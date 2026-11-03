"""Boot a real isolated HA process; no pytest fixture or radio mock is used."""

import argparse
import asyncio
import json
from importlib import metadata
import logging
from pathlib import Path
import shutil
from types import MappingProxyType

from packaging.requirements import Requirement

from homeassistant import bootstrap, loader, runner
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    STORAGE_KEY,
    STORAGE_VERSION,
    STORAGE_VERSION_MINOR,
)
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import CoreState
from homeassistant.helpers.json import json_bytes

ADDRESS = "AA:BB:CC:DD:EE:FF"


def prepare(config: Path, source: Path, phase: str) -> None:
    config.mkdir(parents=True, exist_ok=True)
    if phase == "cold":
        if (config / ".storage").exists():
            raise RuntimeError("Cold boot requires an empty configuration")
        (config / "configuration.yaml").write_text(
            "homeassistant:\n  name: LINAK CI\nlogger:\n  default: warning\n"
        )
        shutil.copytree(
            source,
            config / "custom_components" / "ha_linak",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        entry = ConfigEntry(
            domain="ha_linak",
            title="CI desk",
            data={"address": ADDRESS},
            options={},
            version=1,
            minor_version=1,
            source="user",
            unique_id=ADDRESS,
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
        )
        storage = config / ".storage"
        storage.mkdir()
        (storage / "core.config_entries").write_bytes(
            json_bytes(
                {
                    "version": STORAGE_VERSION,
                    "minor_version": STORAGE_VERSION_MINOR,
                    "key": STORAGE_KEY,
                    "data": {"entries": [entry.as_storage_fragment]},
                }
            )
        )
    elif not (config / ".storage" / "core.config_entries").exists():
        raise RuntimeError("Restart requires persisted config entries")


async def run(args) -> None:
    if HA_VERSION != args.expected_version:
        raise RuntimeError("Image version does not match the smoke target")
    manifest = json.loads((args.source / "manifest.json").read_text())
    for specification in manifest["requirements"]:
        requirement = Requirement(specification)
        installed = metadata.version(requirement.name)
        if not requirement.specifier.contains(installed, prereleases=True):
            raise RuntimeError(f"Image does not satisfy {requirement.name} requirement")
    prepare(args.config, args.source, args.phase)
    hass = None
    errors = []

    class ErrorCapture(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append({"logger": record.name, "message": record.getMessage()})

    error_handler = ErrorCapture()
    logging.getLogger().addHandler(error_handler)
    console_handler = logging.StreamHandler()
    logging.getLogger().addHandler(console_handler)
    report = {"ha_version": HA_VERSION, "phase": args.phase, "success": False}
    try:
        async with asyncio.timeout(120):
            hass = await bootstrap.async_setup_hass(
                runner.RuntimeConfig(
                    config_dir=str(args.config),
                    skip_pip=True,
                    log_no_color=True,
                )
            )
            if hass is None or hass.config.recovery_mode:
                raise RuntimeError("HA bootstrap entered recovery mode or failed")
            await hass.async_start()
            await hass.async_block_till_done(wait_background_tasks=True)
            entries = hass.config_entries.async_entries("ha_linak")
            if len(entries) != 1:
                raise RuntimeError("Synthetic LINAK entry was not restored")
            entry = entries[0]
            report.update(core_state=hass.state.name, entry_state=entry.state.name)
            if hass.state is not CoreState.running:
                raise RuntimeError("HA did not reach running")
            if entry.state is not ConfigEntryState.SETUP_RETRY:
                raise RuntimeError(
                    f"Expected unavailable-desk retry, got {entry.state.name}"
                )
            # A loader/config dependency error must never masquerade as missing radio.
            if entry.error_reason_translation_key not in (None, "startup_waiting"):
                raise RuntimeError("Unexpected startup failure category")
            if entry.reason != "Desk is not reachable through Bluetooth":
                raise RuntimeError("Unexpected retry reason for a radio-free instance")
            integration = await loader.async_get_integration(hass, "ha_linak")
            component = await integration.async_get_component()
            platforms = [str(platform) for platform in component.PLATFORMS]
            for platform in [*platforms, "config_flow", "diagnostics"]:
                await integration.async_get_platform(platform)
            report["platforms_imported"] = platforms
            report["readings_validated"] = False
            report["success"] = True
    finally:
        if hass is not None:
            async with asyncio.timeout(30):
                await hass.async_stop()
        report["errors"] = errors
        report["success"] = report["success"] and not errors
        await asyncio.to_thread(
            args.report.write_text, json.dumps(report, indent=2) + "\n"
        )
        logging.getLogger().removeHandler(error_handler)
        logging.getLogger().removeHandler(console_handler)
    print(json.dumps(report))
    if errors:
        raise RuntimeError("HA reported errors during boot or shutdown")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--phase", choices=("cold", "restart"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    with asyncio.Runner(loop_factory=runner.create_event_loop) as process_runner:
        process_runner.run(run(args))


if __name__ == "__main__":
    main()
