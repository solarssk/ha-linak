"""Protocol checks run without Home Assistant or hardware."""

import importlib.util
from pathlib import Path
import sys
import unittest

path = Path(__file__).resolve().parents[1] / "custom_components/ha_linak/protocol.py"
spec = importlib.util.spec_from_file_location("linak_protocol", path)
protocol = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = protocol
spec.loader.exec_module(protocol)


class ProtocolTests(unittest.TestCase):
    def test_hardware_capture_preserves_raw_words(self):
        sample = protocol.decode_position(bytes.fromhex("9e050000"))
        self.assertEqual(sample.position_raw, 1438)
        self.assertEqual(sample.speed_raw, 0)
        self.assertAlmostEqual(sample.height_m(0.62), 0.7638)
        self.assertAlmostEqual(sample.height_m(0.70), 0.8438)

    def test_speed_flags_are_not_lost(self):
        sample = protocol.decode_position(bytes.fromhex("010001f0"))
        self.assertEqual(sample.speed_raw, 0xF001)

    def test_malformed_frame_is_rejected(self):
        for payload in (b"", b"\x01", bytes(3), bytes(5)):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                protocol.decode_position(payload)

    def test_queries_match_independently_observed_framing(self):
        self.assertEqual(
            protocol.read_request(protocol.ReadCommand.CAPABILITIES),
            bytes.fromhex("7f8000"),
        )
        self.assertEqual(
            protocol.read_request(protocol.ReadCommand.MEMORY_4),
            bytes.fromhex("7f8c00"),
        )

    def test_arbitrary_commands_cannot_be_encoded(self):
        for command in (0x80, 0xFF, "OFFSET", None):
            with self.subTest(command=command), self.assertRaises(ValueError):
                protocol.read_request(command)


if __name__ == "__main__":
    unittest.main()
