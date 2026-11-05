"""Coverage-guided fuzzing for pure LINAK protocol decoders."""

import argparse
from collections.abc import Callable
from pathlib import Path
import sys
import tempfile

import atheris

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "custom_components/ha_linak"
sys.path.insert(0, str(PROTOCOL_PATH))

with atheris.instrument_imports():
    import protocol


@atheris.instrument_func
def _check_decoder(
    decoder: Callable[[bytes], object],
    data: bytes,
    result_types: tuple[type, ...],
) -> None:
    try:
        result = decoder(data)
    except ValueError:
        return
    if not isinstance(result, result_types):
        raise AssertionError(f"{decoder.__name__} returned an unexpected result")
    if isinstance(result, protocol.PositionSample) and not (
        0 <= result.position_raw < 0xFFFF and 0 <= result.speed_raw <= 0xFFFF
    ):
        raise AssertionError("PositionSample contains an out-of-range word")
    if isinstance(result, protocol.StoredPosition):
        if result.position_raw is not None and not 0 <= result.position_raw <= 0xFFFF:
            raise AssertionError("Stored position contains an out-of-range position")
        if not 0 <= result.counter_raw <= 0xFFFFFFFF:
            raise AssertionError("Stored position contains an out-of-range counter")
    if isinstance(result, int) and not 0 <= result <= 0xFFFF:
        raise AssertionError("Offset contains an out-of-range word")
    if isinstance(result, protocol.ReminderSettings):
        if len(result.profiles_raw) != 3 or any(
            not 0 <= value <= 0xFF for pair in result.profiles_raw for value in pair
        ):
            raise AssertionError("Reminder settings contain invalid interval bytes")
        if not 0 <= result.counter_raw <= 0xFFFFFFFF:
            raise AssertionError("Reminder settings contain an invalid counter")
    if decoder is protocol.research_product_reply and isinstance(result, bytes):
        if result != data:
            raise AssertionError("Research response bytes were not preserved")
    if decoder is protocol.activation_request and isinstance(result, bytes):
        if not result.startswith(b"\x7f\x86\x80\x01") or len(result) != 20:
            raise AssertionError("Activation request changed the client identity")


@atheris.instrument_func
def TestOneInput(data: bytes) -> None:
    _check_decoder(protocol.decode_position, data, (protocol.PositionSample,))
    _check_decoder(protocol.decode_capabilities, data, (protocol.Capabilities,))
    _check_decoder(protocol.decode_stored_position, data, (protocol.StoredPosition,))
    _check_decoder(protocol.decode_offset, data, (int, type(None)))
    _check_decoder(protocol.decode_reminders, data, (protocol.ReminderSettings,))
    _check_decoder(protocol.research_product_reply, data, (bytes, type(None)))
    _check_decoder(protocol.activation_request, data, (bytes, type(None)))


def _seed_corpus(directory: Path) -> None:
    seeds = (
        b"",
        b"\x01\x00",
        b"\x01\x02\x00\x00",
        b"\x01\x02\xff\xff",
        b"\x01\x03\x01\x00\x00",
        b"\x01\x07\x00" + bytes(4),
        b"\x01\x07\x01" + bytes(6),
        b"\x01\x0b" + bytes(11),
        b"\x01\x11\x00\x01" + bytes(15),
        bytes(4),
        b"\xff" * 19,
    )
    for index, seed in enumerate(seeds):
        (directory / f"seed-{index:02}").write_bytes(seed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.duration_seconds <= 300:
        parser.error("--duration-seconds must be between 1 and 300")

    with tempfile.TemporaryDirectory(prefix="ha-linak-fuzz-") as temporary:
        corpus = Path(temporary)
        _seed_corpus(corpus)
        atheris.Setup(
            [
                sys.argv[0],
                str(corpus),
                f"-max_total_time={args.duration_seconds}",
            ],
            TestOneInput,
        )
        atheris.Fuzz()


if __name__ == "__main__":
    main()
