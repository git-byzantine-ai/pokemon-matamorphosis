import unittest
from pathlib import Path
from scripts.package_build import ips


def apply_ips(original, patch):
    result = bytearray(original)
    assert patch[:5] == b'PATCH'
    position = 5
    while patch[position:position+3] != b'EOF':
        offset = int.from_bytes(patch[position:position+3], 'big')
        size = int.from_bytes(patch[position+3:position+5], 'big')
        position += 5
        assert size > 0
        result[offset:offset+size] = patch[position:position+size]
        position += size
    return bytes(result)


class PatchTests(unittest.TestCase):
    def test_reserved_offset_and_maximum_record_length(self):
        original = bytes(0x454f46 + 65540)
        modified = bytearray(original)
        modified[0x454f46:0x454f46+65535] = b'\x01' * 65535
        self.assertEqual(apply_ips(original, ips(original, modified)), bytes(modified))

    def test_actual_16_mib_rom_round_trip(self):
        root = Path(__file__).resolve().parents[1]
        original = (root / 'build/firered-baseline.gba').read_bytes()
        expected = (root / 'build/firered-metamorphosis.gba').read_bytes()
        patch = (root / 'build/firered-metamorphosis.ips').read_bytes()
        self.assertEqual(len(expected), 16 * 1024 * 1024)
        self.assertEqual(apply_ips(original, patch), expected)

    def test_essence_bundle_round_trip(self):
        root=Path(__file__).resolve().parents[1]/'build'
        original=(root/'firered-baseline.gba').read_bytes()
        expected=(root/'essence-update/firered-metamorphosis.gba').read_bytes()
        patch=(root/'essence-update/firered-metamorphosis.ips').read_bytes()
        self.assertEqual(apply_ips(original,patch),expected)

    def test_refund_bundle_round_trip(self):
        root=Path(__file__).resolve().parents[1]/'build'
        original=(root/'firered-baseline.gba').read_bytes()
        expected=(root/'refund-update/firered-metamorphosis.gba').read_bytes()
        patch=(root/'refund-update/firered-metamorphosis.ips').read_bytes()
        self.assertEqual(apply_ips(original,patch),expected)

    def test_triple_bundle_round_trip(self):
        root=Path(__file__).resolve().parents[1]/'build'
        original=(root/'firered-baseline.gba').read_bytes()
        expected=(root/'triple-update/firered-metamorphosis.gba').read_bytes()
        patch=(root/'triple-update/firered-metamorphosis.ips').read_bytes()
        self.assertEqual(apply_ips(original,patch),expected)
