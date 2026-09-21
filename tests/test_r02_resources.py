"""Tests for the R02 resource-sampling labels and failure recording (issue #17).

The probes are injected fakes. Nothing here reads the GPU or the host.
"""

import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

from scripts.r02_gate import REDACTED
from scripts.r02_preflight import UNSET
from scripts.r02_resources import (
    KIND,
    PEAK_COUNTER,
    SAMPLE,
    SAMPLE_ERROR,
    SAMPLE_OK,
    STATUS_DEGRADED,
    STATUS_OK,
    Probe,
    ResourceSampler,
    default_probes,
    main,
    memory_probe,
    nvidia_smi_probe,
    summarize,
    torch_peak_probe,
)

MEMINFO = "MemTotal:       24613612 kB\nMemFree:         1000000 kB\nMemAvailable:   23894208 kB\n"


class StepClock:
    def __init__(self, stamps):
        self._stamps = list(stamps)
        self._last = None

    def __call__(self):
        if self._stamps:
            self._last = self._stamps.pop(0)
        return self._last


def probe(name, kind, metrics, values, units=None, basis=UNSET):
    return Probe(
        name=name,
        command=f"{name} --query",
        kind=kind,
        units=units or {metric: "MiB" for metric in metrics},
        read=lambda: dict(zip(metrics, values)),
        basis=basis,
    )


def exploding_probe(name="nvidia-smi", message="nvidia-smi not found (simulated)"):
    def boom():
        raise FileNotFoundError(message)

    return Probe(
        name=name,
        command="nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits",
        kind=SAMPLE,
        units={"vram_used_mib": "MiB"},
        read=boom,
    )


class SamplerTests(unittest.TestCase):
    def test_one_instant_shares_a_timestamp_and_names_its_probe(self):
        sampler = ResourceSampler(
            [probe("gpu", SAMPLE, ("vram_used_mib",), (900.0,))],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        )
        samples = sampler.sample_once()
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].timestamp_utc, "2026-09-21T03:00:00Z")
        self.assertEqual(samples[0].source, "gpu")
        self.assertEqual(samples[0].units, "MiB")
        self.assertEqual(samples[0].status, SAMPLE_OK)
        self.assertEqual(samples[0].error, UNSET)
        self.assertEqual(sampler.probe_errors, [])

    def test_each_instant_gets_its_own_timestamp(self):
        sampler = ResourceSampler(
            [probe("gpu", SAMPLE, ("vram_used_mib",), (900.0,))],
            clock=StepClock(["2026-09-21T03:00:00Z", "2026-09-21T03:00:05Z"]),
        )
        sampler.sample_once()
        sampler.sample_once()
        stamps = [sample.timestamp_utc for sample in sampler.samples]
        self.assertEqual(stamps, ["2026-09-21T03:00:00Z", "2026-09-21T03:00:05Z"])

    def test_an_unreadable_probe_records_error_samples_instead_of_raising(self):
        sampler = ResourceSampler(
            [exploding_probe()], clock=StepClock(["2026-09-21T03:00:00Z"])
        )
        samples = sampler.sample_once()  # must not raise
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].status, SAMPLE_ERROR)
        self.assertEqual(samples[0].value, UNSET)
        self.assertIn("nvidia-smi not found", samples[0].error)
        self.assertEqual(len(sampler.probe_errors), 1)
        self.assertEqual(sampler.probe_errors[0]["source"], "nvidia-smi")
        self.assertEqual(sampler.probe_errors[0]["timestamp_utc"], "2026-09-21T03:00:00Z")

    def test_probe_errors_are_redacted(self):
        sampler = ResourceSampler(
            [exploding_probe(message="query failed: token=abc123def")],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        )
        sampler.sample_once()
        error = sampler.sample_once()[0].error
        self.assertIn(REDACTED, error)
        self.assertNotIn("abc123def", error)

    def test_a_probe_that_is_missing_entirely_still_yields_its_declared_metrics(self):
        def missing():
            raise FileNotFoundError("nvidia-smi")

        sampler = ResourceSampler(
            [
                Probe(
                    name="nvidia-smi",
                    command="nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits",
                    kind=SAMPLE,
                    units={"vram_used_mib": "MiB", "vram_total_mib": "MiB"},
                    read=missing,
                )
            ],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        )
        metrics = sorted(sample.metric for sample in sampler.sample_once())
        self.assertEqual(metrics, ["vram_total_mib", "vram_used_mib"])


class SummaryLabelTests(unittest.TestCase):
    def test_sampled_only_metrics_leave_the_peak_unset(self):
        samples = ResourceSampler(
            [probe("gpu", SAMPLE, ("vram_used_mib",), (900.0,))],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        ).sample_once()
        summary = summarize(samples, probes=default_probes(), interval_seconds=5.0)
        self.assertEqual(summary["kind"], KIND)
        self.assertEqual(summary["status"], STATUS_OK)
        self.assertEqual(summary["peak_claims"]["vram_used_mib"]["value"], UNSET)
        self.assertIn("not measured", summary["peak_claims"]["vram_used_mib"]["basis"])
        self.assertEqual(summary["peak_claims"]["vram_used_mib"]["source_kind"], SAMPLE)
        self.assertEqual(summary["sampled"]["vram_used_mib"]["sampled_max"], 900.0)
        self.assertIn("not a peak", summary["labels"]["sampled_max"])
        self.assertEqual(summary["method"]["interval_seconds"], 5.0)
        self.assertEqual(summary["method"]["instant_count"], 1)

    def test_peak_counter_metrics_fill_the_peak_claim_and_name_their_window(self):
        basis = "reset immediately before the measured window; covers that window only"
        sampler = ResourceSampler(
            [probe("torch", PEAK_COUNTER, ("vram_peak_allocated_mib",), (4200.0,), basis=basis)],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        )
        samples = sampler.sample_once()
        summary = summarize(samples, probes=sampler.probes)
        claim = summary["peak_claims"]["vram_peak_allocated_mib"]
        self.assertEqual(claim["value"], 4200.0)
        self.assertEqual(claim["source_kind"], PEAK_COUNTER)
        self.assertEqual(claim["basis"], basis)
        self.assertEqual(summary["peak_labelled_metrics"], ["vram_peak_allocated_mib"])
        self.assertEqual(summary["method"]["probes"][0]["basis"], basis)

    def test_a_recorded_probe_error_degrades_the_summary_and_keeps_the_peak_unset(self):
        sampler = ResourceSampler(
            [exploding_probe()], clock=StepClock(["2026-09-21T03:00:00Z"])
        )
        samples = sampler.sample_once()
        summary = sampler.summary(interval_seconds=UNSET)
        self.assertEqual(summary["status"], STATUS_DEGRADED)
        self.assertEqual(summary["peak_claims"]["vram_used_mib"]["value"], UNSET)
        self.assertEqual(summary["sampled"]["vram_used_mib"]["readings"], 0)
        self.assertEqual(summary["sampled"]["vram_used_mib"]["errors"], 1)
        self.assertEqual(summary["sampled"]["vram_used_mib"]["sampled_max"], UNSET)
        self.assertEqual(len(summary["probe_errors"]), 1)
        self.assertEqual(len(samples), 1)
        json.dumps(summary)  # the degraded summary must still be recordable

    def test_samples_keep_their_own_records(self):
        samples = ResourceSampler(
            [probe("gpu", SAMPLE, ("vram_used_mib",), (901.0,))],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        ).sample_once()
        summary = summarize(samples, probes=(), interval_seconds=UNSET)
        self.assertEqual(summary["samples"][0]["metric"], "vram_used_mib")
        self.assertEqual(summary["samples"][0]["value"], 901.0)
        self.assertEqual(summary["method"]["interval_seconds"], UNSET)
        json.dumps(summary)

    def test_default_probes_are_allocation_free(self):
        kinds = {probe.kind for probe in default_probes()}
        self.assertEqual(kinds, {SAMPLE})
        self.assertNotIn("torch.cuda peak counters", {probe.name for probe in default_probes()})


class ProbeTests(unittest.TestCase):
    def test_nvidia_smi_probe_parses_the_query(self):
        captured = {}

        def runner(argv, **kwargs):
            captured["argv"] = argv
            return SimpleNamespace(stdout="993, 10240, 12\n", returncode=0)

        values = nvidia_smi_probe(runner=runner).read()
        self.assertEqual(values["vram_used_mib"], 993.0)
        self.assertEqual(values["vram_total_mib"], 10240.0)
        self.assertEqual(values["gpu_utilization_pct"], 12.0)
        self.assertEqual(captured["argv"][0], "nvidia-smi")
        self.assertIn("--format=csv,noheader,nounits", captured["argv"])

    def test_missing_nvidia_smi_is_caught_by_the_sampler(self):
        def runner(*args, **kwargs):
            raise FileNotFoundError("[Errno 2] No such file or directory: 'nvidia-smi'")

        sampler = ResourceSampler(
            [nvidia_smi_probe(runner=runner)], clock=StepClock(["2026-09-21T03:00:00Z"])
        )
        samples = sampler.sample_once()
        self.assertEqual(len(samples), 3)
        self.assertTrue(all(sample.status == SAMPLE_ERROR for sample in samples))
        self.assertEqual(sampler.probe_errors[0]["source"], "nvidia-smi")

    def test_memory_probe_reads_meminfo(self):
        values = memory_probe(reader=lambda: MEMINFO).read()
        self.assertAlmostEqual(values["ram_available_mib"], 23894208 / 1024.0)
        self.assertAlmostEqual(values["ram_total_mib"], 24613612 / 1024.0)

    def test_torch_peak_probe_takes_an_injected_module(self):
        class FakeCuda:
            @staticmethod
            def max_memory_allocated():
                return 1024 * 1024 * 3

            @staticmethod
            def max_memory_reserved():
                return 1024 * 1024 * 4

        values = torch_peak_probe(torch_module=SimpleNamespace(cuda=FakeCuda)).read()
        self.assertEqual(values["vram_peak_allocated_mib"], 3.0)
        self.assertEqual(values["vram_peak_reserved_mib"], 4.0)

    def test_probe_record_states_the_exact_command_and_window(self):
        record = torch_peak_probe(torch_module=SimpleNamespace()).to_record()
        self.assertIn("reset_peak_memory_stats", record["command"])
        self.assertIn("reset at run start", record["basis"])
        self.assertEqual(record["kind"], PEAK_COUNTER)


class ResourcesCliTests(unittest.TestCase):
    def test_probe_failure_is_a_record_and_a_nonzero_exit_not_a_traceback(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(
                ["probe", "--instants", "2"],
                sampler_factory=lambda: ResourceSampler(
                    [exploding_probe()],
                    clock=StepClock(["2026-09-21T03:00:00Z", "2026-09-21T03:00:05Z"]),
                ),
            )
        self.assertEqual(code, 1)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], STATUS_DEGRADED)
        self.assertEqual(payload["kind"], KIND)
        self.assertEqual(len(payload["probe_errors"]), 2)
        self.assertEqual(len(payload["samples"]), 2)
        self.assertEqual(payload["peak_claims"]["vram_used_mib"]["value"], UNSET)

    def test_readable_probes_exit_zero(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(
                ["probe"],
                sampler_factory=lambda: ResourceSampler(
                    [probe("gpu", SAMPLE, ("vram_used_mib",), (900.0,))],
                    clock=StepClock(["2026-09-21T03:00:00Z"]),
                ),
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buffer.getvalue())["status"], STATUS_OK)


if __name__ == "__main__":
    unittest.main()
