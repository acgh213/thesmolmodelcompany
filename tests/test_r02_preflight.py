import hashlib
import tempfile
import unittest
from pathlib import Path
from scripts.r02_preflight import build_manifest, persistence_round_trip, sha256_stream

class R02PreflightTests(unittest.TestCase):
    def test_streaming_hash_matches_hashlib(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'payload.bin'
            path.write_bytes(bytes(range(256)) * 4097)
            self.assertEqual(sha256_stream(path), hashlib.sha256(path.read_bytes()).hexdigest())
    def test_persistence_round_trip_reads_back_hash_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.bin'
            source.write_bytes(b'round-trip\\0' * 1000)
            storage = Path(tmp) / 'storage'
            result = persistence_round_trip(source, storage)
            self.assertEqual(result['source_sha256'], result['readback_sha256'])
            self.assertEqual(result['source_bytes'], result['readback_bytes'])
            self.assertFalse((storage / source.name).exists())
    def test_manifest_marks_unknown_fields_explicitly(self):
        manifest = build_manifest()
        self.assertEqual(manifest['model'], 'UNSET')
        self.assertEqual(manifest['measurements']['peak_vram_mib'], 'UNSET')
        self.assertEqual(manifest['timing']['cold_load_seconds'], 'UNSET')

if __name__ == '__main__':
    unittest.main()
