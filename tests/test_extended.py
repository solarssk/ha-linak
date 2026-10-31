"""Extended protocol validation, including real hardware fixtures."""

from test_protocol import protocol
import unittest


class ExtendedTests(unittest.TestCase):
    def test_capabilities_capture(self):
        caps = protocol.decode_capabilities(bytes.fromhex("0102fc01"))
        self.assertEqual(caps.memory_slots, 4)
        self.assertTrue(caps.automatic_up and caps.automatic_down)
        self.assertTrue(caps.display and caps.light and caps.bluetooth)
        self.assertEqual(caps.references_raw, 1)

    def test_offset_capture(self):
        self.assertEqual(protocol.decode_offset(bytes.fromhex("010301901a")), 6800)

    def test_memory_capture(self):
        result = protocol.decode_stored_position(bytes.fromhex("010701b404a45b0000"))
        self.assertEqual(result.position_raw, 1204)
        self.assertEqual(result.counter_raw, 23460)

    def test_empty_memory_has_no_position(self):
        result = protocol.decode_stored_position(bytes.fromhex("01070001000000"))
        self.assertIsNone(result.position_raw)
        self.assertEqual(result.counter_raw, 1)

    def test_reminder_synthetic_frame_preserves_unknown_flags(self):
        result = protocol.decode_reminders(bytes.fromhex("010bff370a320a2d0f78563412"))
        self.assertEqual(result.flags_raw, 255)
        self.assertEqual(result.selected_profile, 3)
        self.assertEqual(result.profiles_raw, ((55, 10), (50, 10), (45, 15)))
        self.assertEqual(result.counter_raw, 0x12345678)

    def test_malformed_frames_and_unknown_validity(self):
        cases = [
            (protocol.decode_capabilities, "0102fc"),
            (protocol.decode_capabilities, "0103fc01"),
            (protocol.decode_offset, "010302901a"),
            (protocol.decode_stored_position, "010701b404"),
            (protocol.decode_stored_position, "01070200000000"),
            (protocol.decode_reminders, "010b20370a2d0f86880000"),
        ]
        for decoder, frame in cases:
            with self.subTest(frame=frame):
                payload = bytes.fromhex(frame)
                with self.assertRaises(ValueError):
                    decoder(payload)


if __name__ == "__main__":
    unittest.main()


class HardwareFixtureTests(unittest.TestCase):
    def test_every_captured_query_has_a_valid_typed_response(self):
        import json
        from pathlib import Path

        capture = json.loads(
            (Path(__file__).parent / "fixtures/dpg1c_read_queries.json").read_text()
        )["responses"]
        self.assertEqual(set(capture), {"80", "81", "88", "89", "8a", "8b", "8c"})
        protocol.decode_capabilities(bytes.fromhex(capture["80"]))
        offset = protocol.decode_offset(bytes.fromhex(capture["81"]))
        self.assertEqual(offset, 6800)
        for key, expected in zip(("89", "8a", "8b", "8c"), (1204, 1438, 5152, 5696)):
            self.assertEqual(
                protocol.decode_stored_position(
                    bytes.fromhex(capture[key])
                ).position_raw,
                expected,
            )
        reminder = protocol.decode_reminders(bytes.fromhex(capture["88"]))
        self.assertEqual(reminder.selected_profile, 3)
        self.assertEqual(reminder.profiles_raw, ((55, 5), (50, 10), (45, 15)))

    def test_every_truncated_capture_is_rejected(self):
        import json
        from pathlib import Path

        capture = json.loads(
            (Path(__file__).parent / "fixtures/dpg1c_read_queries.json").read_text()
        )["responses"]
        decoders = {
            "80": protocol.decode_capabilities,
            "81": protocol.decode_offset,
            "88": protocol.decode_reminders,
        }
        for key, frame in capture.items():
            decoder = decoders.get(key, protocol.decode_stored_position)
            data = bytes.fromhex(frame)
            for end in range(len(data)):
                with (
                    self.subTest(command=key, length=end),
                    self.assertRaises(ValueError),
                ):
                    decoder(data[:end])
