#!/usr/bin/env python3
"""R02.1 resource sampling with honest sampled-versus-peak labels.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/17.

``docs/compute.md`` requires "sampling method and whether a value describes the
GPU or the whole desktop", and this repository has already been bitten by
restating a drift-prone reading as a constant. So sampling and peak claims are
separated in the data itself:

* every observation carries its own UTC timestamp, its probe, and the exact
  command or source it came from;
* a metric is labelled a **peak** only when a device peak *counter* produced it,
  and the recorded basis names the window that counter actually covered. A
  periodic poll yields a **sampled max** and leaves the peak field ``UNSET``
  with a stated basis, because a sampled maximum understates a peak;
* a probe that cannot be read is a *recorded* failure, not an exception: the
  instant produces samples with ``value: UNSET``, ``status: "error"`` and a
  redacted ``error``, the summary is marked ``degraded``, and the entry point
  exits non-zero with that record instead of a traceback. A missing ``nvidia-smi``
  must not be able to destroy the record of the run that needed it.

The two default probes are read-only. Polling them allocates nothing and
reserves nothing, which is why ``probe`` runs as a host audit under
``docs/compute.md`` and is deliberately ungated; the model-touching peak-counter
probe is only ever constructed after the readiness-smoke gate.

Usage, from the repository root:

    python3 scripts/r02_resources.py probe --instants 3 --interval 5 --out FILE

Exit codes: 0 every probe answered, 1 at least one probe failed (the record is
still written), 2 a usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from r02_gate import EXIT_OK, EXIT_STEP_FAILED, redact_secrets
    from r02_preflight import UNSET
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.r02_gate import EXIT_OK, EXIT_STEP_FAILED, redact_secrets
    from scripts.r02_preflight import UNSET

KIND = "r02-resource-sampling"

SAMPLE = "sample"
PEAK_COUNTER = "peak-counter"

SAMPLE_OK = "ok"
SAMPLE_ERROR = "error"

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_FAILED = "failed"

NVIDIA_SMI_COMMAND = (
    "nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu "
    "--format=csv,noheader,nounits"
)
MEMINFO_COMMAND = "/proc/meminfo (MemAvailable, MemTotal)"
TORCH_PEAK_COMMAND = (
    "torch.cuda.reset_peak_memory_stats() before any load, then "
    "max_memory_allocated() / max_memory_reserved() after the generation step"
)
TORCH_PEAK_BASIS = (
    "device peak counter, reset at run start before any load and read after the "
    "generation step: the window covers tokenizer load, model load and generation"
)


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ResourceProbeUnavailable(RuntimeError):
    """A probe could not be read, so a required resource figure is missing."""


@dataclass(frozen=True)
class Probe:
    """One source of readings, with the exact method recorded alongside it."""

    name: str
    command: str
    kind: str
    units: Mapping[str, str]
    read: Callable[[], Mapping[str, float]]
    basis: str = UNSET

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "kind": self.kind,
            "units": dict(self.units),
            "basis": self.basis,
        }


@dataclass(frozen=True)
class Sample:
    """One reading at one instant. An unreadable probe yields ``value: UNSET``."""

    timestamp_utc: str
    source: str
    kind: str
    metric: str
    value: Any
    units: str
    status: str = SAMPLE_OK
    error: str = UNSET

    def to_record(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "source": self.source,
            "kind": self.kind,
            "metric": self.metric,
            "value": self.value,
            "units": self.units,
            "status": self.status,
            "error": self.error,
        }


def nvidia_smi_probe(*, runner: Callable[..., Any] = subprocess.run) -> Probe:
    """Whole-GPU readings from ``nvidia-smi``; the desktop shares this GPU."""

    def read() -> dict[str, float]:
        completed = runner(
            NVIDIA_SMI_COMMAND.split(),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        first = completed.stdout.strip().splitlines()[0]
        used, total, utilization = (part.strip() for part in first.split(",")[:3])
        return {
            "vram_used_mib": float(used),
            "vram_total_mib": float(total),
            "gpu_utilization_pct": float(utilization),
        }

    return Probe(
        name="nvidia-smi",
        command=NVIDIA_SMI_COMMAND,
        kind=SAMPLE,
        units={
            "vram_used_mib": "MiB",
            "vram_total_mib": "MiB",
            "gpu_utilization_pct": "%",
        },
        read=read,
    )


def memory_probe(*, reader: Callable[[], str] | None = None) -> Probe:
    """RAM visible to the execution target, which is not the Windows host's RAM."""

    def default_reader() -> str:
        return Path("/proc/meminfo").read_text(encoding="utf-8")

    source = reader or default_reader

    def read() -> dict[str, float]:
        values: dict[str, float] = {}
        for line in source().splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "MemAvailable:":
                values["ram_available_mib"] = float(parts[1]) / 1024.0
            elif parts[0] == "MemTotal:":
                values["ram_total_mib"] = float(parts[1]) / 1024.0
        return values

    return Probe(
        name="proc-meminfo",
        command=MEMINFO_COMMAND,
        kind=SAMPLE,
        units={"ram_available_mib": "MiB", "ram_total_mib": "MiB"},
        read=read,
    )


def torch_peak_probe(
    *, torch_module: Any = None, basis: str = TORCH_PEAK_BASIS
) -> Probe:
    """Device peak counters. The import happens inside ``read``, after the gate."""

    def read() -> dict[str, float]:
        module = torch_module
        if module is None:
            import torch as module  # noqa: PLC0415 - deferred by design, never in tests

        return {
            "vram_peak_allocated_mib": float(module.cuda.max_memory_allocated()) / 1048576.0,
            "vram_peak_reserved_mib": float(module.cuda.max_memory_reserved()) / 1048576.0,
        }

    return Probe(
        name="torch.cuda peak counters",
        command=TORCH_PEAK_COMMAND,
        kind=PEAK_COUNTER,
        units={"vram_peak_allocated_mib": "MiB", "vram_peak_reserved_mib": "MiB"},
        read=read,
        basis=basis,
    )


def default_probes() -> tuple[Probe, ...]:
    """The allocation-free probes, safe to poll before a model exists."""
    return (nvidia_smi_probe(), memory_probe())


class ResourceSampler:
    """Collects timestamped samples from injected probes.

    ``sample_once`` reads every probe at one instant under a single clock read,
    so samples in one instant share a timestamp rather than drifting apart. It
    never raises: a probe that cannot be read produces error samples and an entry
    in ``probe_errors``, because a missing measurement must be visible in the
    record rather than replace it.
    """

    def __init__(
        self,
        probes: Sequence[Probe] | None = None,
        *,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.probes = tuple(probes) if probes is not None else default_probes()
        self._clock = clock
        self.samples: list[Sample] = []
        self.probe_errors: list[dict[str, Any]] = []

    def add_probe(self, probe: Probe) -> None:
        self.probes = (*self.probes, probe)

    def sample_once(self) -> list[Sample]:
        timestamp = self._clock()
        instant: list[Sample] = []
        for probe in self.probes:
            try:
                readings = probe.read()
                status, error = SAMPLE_OK, UNSET
            except Exception as exc:  # recorded, never propagated: see the docstring
                readings = {metric: UNSET for metric in probe.units}
                status = SAMPLE_ERROR
                error = redact_secrets(exc)
                self.probe_errors.append(
                    {
                        "timestamp_utc": timestamp,
                        "source": probe.name,
                        "command": probe.command,
                        "error": error,
                    }
                )
            for metric, value in readings.items():
                instant.append(
                    Sample(
                        timestamp_utc=timestamp,
                        source=probe.name,
                        kind=probe.kind,
                        metric=metric,
                        value=float(value) if status == SAMPLE_OK else UNSET,
                        units=probe.units.get(metric, UNSET),
                        status=status,
                        error=error,
                    )
                )
        self.samples.extend(instant)
        return instant

    def summary(self, *, interval_seconds: float | None = None) -> dict[str, Any]:
        return summarize(
            self.samples,
            probes=self.probes,
            interval_seconds=interval_seconds,
            probe_errors=self.probe_errors,
        )


def summarize(
    samples: Sequence[Sample],
    *,
    probes: Sequence[Probe] = (),
    interval_seconds: float | None = None,
    probe_errors: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the record: sampled statistics first, peak claims only where earned."""
    peak_basis: dict[str, str] = {}
    for probe in probes:
        if probe.kind == PEAK_COUNTER:
            for metric in probe.units:
                peak_basis[metric] = probe.basis if probe.basis != UNSET else (
                    f"device peak counter ({probe.name})"
                )

    instants = sorted({sample.timestamp_utc for sample in samples})
    sampled: dict[str, dict[str, Any]] = {}
    peaks: dict[str, dict[str, Any]] = {}
    for metric in sorted({sample.metric for sample in samples}):
        metric_samples = [sample for sample in samples if sample.metric == metric]
        values = [sample.value for sample in metric_samples if sample.status == SAMPLE_OK]
        first = metric_samples[0]
        sampled[metric] = {
            "count": len(metric_samples),
            "readings": len(values),
            "errors": len(metric_samples) - len(values),
            "units": first.units,
            "source": first.source,
            "first": values[0] if values else UNSET,
            "last": values[-1] if values else UNSET,
            "min": min(values) if values else UNSET,
            "sampled_max": max(values) if values else UNSET,
        }
        if metric in peak_basis:
            basis = peak_basis[metric]
            peaks[metric] = {
                "value": max(values) if values else UNSET,
                "basis": basis if values else f"{basis} (no reading was available)",
                "source_kind": PEAK_COUNTER,
                "units": first.units,
            }
        else:
            peaks[metric] = {
                "value": UNSET,
                "basis": (
                    "not measured: only periodic samples are available, so the "
                    "sampled_max is a lower bound on any peak"
                ),
                "source_kind": SAMPLE,
                "units": first.units,
            }

    errors = [dict(entry) for entry in probe_errors]
    return {
        "kind": KIND,
        "status": STATUS_DEGRADED if errors else STATUS_OK,
        "method": {
            "clock": "system UTC clock, read once per sampling instant",
            "interval_seconds": interval_seconds if interval_seconds is not None else UNSET,
            "instant_count": len(instants),
            "instants": instants,
            "probes": [probe.to_record() for probe in probes],
        },
        "sampled": sampled,
        "peak_claims": peaks,
        "peak_labelled_metrics": sorted(peak_basis),
        "labels": {
            "sampled_max": "maximum over the sampled instants only; not a peak measurement",
            "peak_claims": "filled in only from a device peak counter, and the basis names the window it covered",
            "scope": "GPU figures describe the shared GPU, RAM figures describe the execution target",
            "errors": "a sample with status 'error' carries no reading: value UNSET and a redacted error",
        },
        "probe_errors": errors,
        "samples": [sample.to_record() for sample in samples],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only resource sampling (host audit; allocates and reserves nothing)."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="sample the default read-only probes")
    probe.add_argument("--instants", type=int, default=1)
    probe.add_argument("--interval", type=float, default=0.0, help="seconds between instants")
    probe.add_argument("--out", default=None)
    return parser


def main(argv: Sequence[str] | None = None, *, sampler_factory: Callable[[], ResourceSampler] = ResourceSampler) -> int:
    """Sample and write the record. A probe failure is recorded, not raised.

    ``sampler_factory`` is a test seam: the tests drive this entry point with a
    failing probe without depending on the host's hardware.
    """
    args = build_parser().parse_args(argv)

    try:
        sampler = sampler_factory()
        for index in range(max(1, args.instants)):
            if index and args.interval > 0:
                import time

                time.sleep(args.interval)
            sampler.sample_once()
        payload = sampler.summary(interval_seconds=args.interval or None)
    except Exception as exc:  # last resort: a record, never a traceback
        payload = {
            "kind": KIND,
            "status": STATUS_FAILED,
            "error": redact_secrets(exc),
            "probe_errors": [],
            "samples": [],
        }

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)

    return EXIT_OK if payload["status"] == STATUS_OK else EXIT_STEP_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
