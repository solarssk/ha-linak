"""Failure injection for smoke reports and Docker cleanup, without real Docker."""

from importlib.util import module_from_spec, spec_from_file_location
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import subprocess

import pytest

from scripts import run_ha_smoke

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def smoke():
    spec = spec_from_file_location("linak_boot_smoke", ROOT / "tests/smoke/boot_ha.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def args(tmp_path, smoke):
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text('{"requirements": []}')
    return SimpleNamespace(
        expected_version=smoke.HA_VERSION,
        phase="cold",
        source=source,
        config=tmp_path / "config",
        report=tmp_path / "report.json",
    )


@pytest.mark.parametrize("failure", ["version", "requirement", "prepare"])
async def test_prebootstrap_failure_leaves_report_and_removes_handlers(
    smoke, args, monkeypatch, failure
):
    if failure == "version":
        args.expected_version = "invalid-version"
    elif failure == "requirement":
        (args.source / "manifest.json").write_text(
            '{"requirements": ["ha-linak-nonexistent-package==1"]}'
        )
    else:
        monkeypatch.setattr(
            smoke, "prepare", Mock(side_effect=OSError("config failure"))
        )
    handlers = list(logging.getLogger().handlers)
    with pytest.raises((RuntimeError, smoke.metadata.PackageNotFoundError, OSError)):
        await smoke.run(args)
    report = json.loads(args.report.read_text())
    assert report["success"] is False
    assert "Startup failed:" in report["errors"][0]["message"]
    assert logging.getLogger().handlers == handlers


@pytest.mark.parametrize(
    "failure", [TimeoutError("stop deadline"), RuntimeError("stop")]
)
async def test_shutdown_failure_is_recorded_and_fails_run(
    smoke, args, monkeypatch, failure
):
    monkeypatch.setattr(smoke, "prepare", Mock())
    entry = SimpleNamespace(
        state=smoke.ConfigEntryState.SETUP_RETRY,
        error_reason_translation_key=None,
        reason="Desk is not reachable through Bluetooth",
    )
    hass = SimpleNamespace(
        config=SimpleNamespace(recovery_mode=False),
        state=smoke.CoreState.running,
        async_start=AsyncMock(),
        async_block_till_done=AsyncMock(),
        async_stop=AsyncMock(side_effect=failure),
        config_entries=SimpleNamespace(async_entries=Mock(return_value=[entry])),
    )
    monkeypatch.setattr(
        smoke.bootstrap, "async_setup_hass", AsyncMock(return_value=hass)
    )
    integration = SimpleNamespace(
        async_get_component=AsyncMock(
            return_value=SimpleNamespace(
                PLATFORMS=["sensor", "binary_sensor", "number", "button", "switch"]
            )
        ),
        async_get_platform=AsyncMock(),
    )
    monkeypatch.setattr(
        smoke.loader, "async_get_integration", AsyncMock(return_value=integration)
    )
    handlers = list(logging.getLogger().handlers)
    with pytest.raises(RuntimeError, match="HA reported errors"):
        await smoke.run(args)
    report = json.loads(args.report.read_text())
    assert report["success"] is False
    assert "Shutdown failed:" in report["errors"][0]["message"]
    assert logging.getLogger().handlers == handlers


def test_container_removal_timeout_does_not_skip_network_removal(monkeypatch, capsys):
    remove = Mock(
        side_effect=[subprocess.TimeoutExpired("docker rm", 30), Mock(returncode=0)]
    )
    monkeypatch.setattr(run_ha_smoke.subprocess, "run", remove)
    run_ha_smoke.cleanup_resources("ci-container", "ci-network")
    assert remove.call_count == 2
    assert remove.call_args_list[1].args[0] == ["docker", "network", "rm", "ci-network"]
    assert "Cleanup failed for ci-container" in capsys.readouterr().err
