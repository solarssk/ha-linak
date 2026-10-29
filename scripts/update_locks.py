"""Reproduce Linux/Python 3.14 CI locks using a versioned uv resolver."""

import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCKS = {
    "uv": ".github/requirements-locker.txt",
    "audit": "requirements-tools.txt",
    "test": "requirements-dev.txt",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    version = subprocess.check_output(["uv", "--version"], text=True).split()[1]
    expected = (
        (ROOT / ".github/requirements-locker.txt")
        .read_text()
        .strip()
        .removeprefix("uv==")
    )
    if version != expected:
        raise ValueError(f"Use uv {expected} to reproduce the committed locks")
    for name, source in LOCKS.items():
        destination = ROOT / ".github/locks" / f"{name}.txt"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / f"{name}.txt"
            # Preserve existing transitive pins. A freshness check must not mean upgrading
            # everything released since yesterday; explicit input changes still resolve.
            if destination.exists():
                output.write_bytes(destination.read_bytes())
            command = [
                "uv",
                "pip",
                "compile",
                source,
                "--python-version",
                "3.14.2",
                "--python-platform",
                "x86_64-manylinux_2_39",
                "--generate-hashes",
                "--custom-compile-command",
                "python scripts/update_locks.py",
                "--output-file",
                str(output),
                "--quiet",
            ]
            subprocess.run(command, cwd=ROOT, check=True)
            content = output.read_bytes()
        if args.check:
            if not destination.exists() or destination.read_bytes() != content:
                raise ValueError(
                    f"Stale {destination.relative_to(ROOT)}; regenerate locks"
                )
        else:
            destination.write_bytes(content)
    print("All CI dependency locks match their source inputs")


if __name__ == "__main__":
    main()
