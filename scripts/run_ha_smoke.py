"""Cold boot and restart pinned HA images without host networking or hardware."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("supported", "preview"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = json.loads((ROOT / ".github/ha-smoke-targets.json").read_text())[
        args.target
    ]
    image = target["image"]
    if not re.fullmatch(
        r"ghcr\.io/home-assistant/home-assistant:[a-zA-Z0-9.]+@sha256:[a-f0-9]{64}",
        image,
    ):
        raise ValueError("Smoke target must be a pinned official HA image")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    network = f"linak-smoke-{uuid.uuid4().hex}"
    container = network + "-ha"

    def command(argv, logfile, timeout=180):
        with (output / logfile).open("w") as log:
            subprocess.run(
                argv, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout
            )

    command(["docker", "pull", image], "pull.log", timeout=600)
    try:
        command(["docker", "network", "create", "--internal", network], "network.log")
        with tempfile.TemporaryDirectory(prefix="linak-smoke-") as config:
            for phase in ("cold", "restart"):
                command(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--name",
                        container,
                        "--user",
                        f"{os.getuid()}:{os.getgid()}",
                        "--network",
                        network,
                        "--cap-drop",
                        "ALL",
                        "--security-opt",
                        "no-new-privileges",
                        "--pids-limit",
                        "256",
                        "--memory",
                        "2g",
                        "--entrypoint",
                        "python",
                        "-v",
                        f"{ROOT}:/repo:ro",
                        "-v",
                        f"{config}:/config",
                        "-v",
                        f"{output}:/results",
                        image,
                        "/repo/tests/smoke/boot_ha.py",
                        "--config",
                        "/config",
                        "--source",
                        "/repo/custom_components/ha_linak",
                        "--expected-version",
                        target["version"],
                        "--phase",
                        phase,
                        "--report",
                        f"/results/{phase}.json",
                    ],
                    f"{phase}.log",
                )
                report = json.loads((output / f"{phase}.json").read_text())
                if not report["success"]:
                    raise RuntimeError(f"HA {phase} smoke failed")
                print(json.dumps(report))
    finally:
        # Only remove resources created by this invocation, even after a deadline.
        subprocess.run(
            ["docker", "rm", "--force", container], capture_output=True, timeout=30
        )
        subprocess.run(
            ["docker", "network", "rm", network], capture_output=True, timeout=30
        )


if __name__ == "__main__":
    main()
