"""Tests for the R02 resource-sampling labels (issue #17).

The probes are injected fakes. Nothing here reads the GPU or the host.
"""

import json
import unittest
from types import SimpleNamespace

from scripts.r02_preflight import UNSET
from scripts.r02_resources import (
    PEAK_COUNTER,
    SAMPLE,
    Probe,
    ResourceSampler,
    default_probes,
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


def probe(name, kind, metrics, values, units=None):
    return Probe(
        name=name,
        command=f"{name} --query",
        kind=kind,
        units=units or {metric: "MiB" for metric in metrics},
        read=lambda: dict(zip(metrics, values)),
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

    def test_each_instant_gets_its_own_timestamp(self):
        sampler = ResourceSampler(
            [probe("gpu", SAMPLE, ("vram_used_mib",), (900.0,))],
            clock=StepClock(["2026-09-21T03:00:00Z", "2026-09-21T03:00:05Z"]),
        )
        sampler.sample_once()
        sampler.sample_once()
        stamps = [sample.timestamp_utc for sample in sampler.samples]
        self.assertEqual(stamps, ["2026-09-21T03:00:00Z", "2026-09-21T03:00:05Z"])


class SummaryLabelTests(unittest.TestCase):
    def test_sampled_only_metrics_leave_the_peak_unset(self):
        samples = ResourceSampler(
            [probe("gpu", SAMPLE, ("vram_used_mib",), (900.0,))],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        ).sample_once()
        summary = summarize(samples, probes=default_probes(), interval_seconds=5.0)
        self.assertEqual(summary["kind"], "r02-resource-sampling")
        self.assertEqual(summary["peak_claims"]["vram_used_mib"]["value"], UNSET)
        self.assertIn("not measured", summary["peak_claims"]["vram_used_mib"]["basis"])
        self.assertEqual(summary["peak_claims"]["vram_used_mib"]["source_kind"], SAMPLE)
        self.assertEqual(summary["sampled"]["vram_used_mib"]["sampled_max"], 900.0)
        self.assertIn("not a peak", summary["labels"]["sampled_max"])
        self.assertEqual(summary["method"]["interval_seconds"], 5.0)
        self.assertEqual(summary["method"]["instant_count"], 1)

    def test_peak_counter_metrics_fill_the_peak_claim(self):
        sampler = ResourceSampler(
            [probe("torch", PEAK_COUNTER, ("vram_peak_allocated_mib",), (4200.0,))],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        )
        samples = sampler.sample_once()
        summary = summarize(samples, probes=sampler.probes)
        self.assertEqual(summary["peak_claims"]["vram_peak_allocated_mib"]["value"], 4200.0)
        self.assertEqual(
            summary["peak_claims"]["vram_peak_allocated_mib"]["source_kind"], PEAK_COUNTER
        )
        self.assertIn("peak counter", summary["peak_claims"]["vram_peak_allocated_mib"]["basis"])
        self.assertEqual(summary["peak_labelled_metrics"], ["vram_peak_allocated_mib"])

    def test_samples_keep_their_own_records(self):
        samples = ResourceSampler(
            [probe("gpu", SAMPLE, ("vram_used_mib",), (901.0,))],
            clock=StepClock(["2026-09-21T03:00:00Z"]),
        ).sample_once()
        summary = summarize(samples, probes=(), interval_seconds=UNSET)
        self.assertEqual(summary["samples"][0]["metric"], "vram_used_mib")
        self.assertEqual(summary["samples"][0]["value"], 901.0)
        self.assertEqual(summary["method"]["interval_seconds"], UNSET)
        json.dumps(summary)  # the summary must be recordable

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

    def test_probe_record_states_the_exact_command(self):
        record = torch_peak_probe(torch_module=SimpleNamespace()).to_record()
        self.assertIn("reset_peak_memory_stats", record["command"])
        self.assertEqual(record["kind"], PEAK_COUNTER)


if __name__ == "__main__":
    unittest.main()
