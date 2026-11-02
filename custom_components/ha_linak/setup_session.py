"""Bounded, in-memory transfer from the setup wizard to its coordinator."""

import asyncio

from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from .client import DeskClient
from .const import DOMAIN
from .motion import _drain_cleanup

_KEY = f"{DOMAIN}_setup_sessions"
HANDOFF_TIMEOUT = 60


@callback
def offer_session(hass: HomeAssistant, desk: DeskClient) -> None:
    """Keep a successful wizard's link until setup consumes it or time expires."""
    sessions = hass.data.setdefault(_KEY, {})
    address = desk.device.address

    @callback
    def expire() -> None:
        session = sessions.pop(address, None)
        if session is not None:
            session[1].cancel()
            session[2]()
            hass.async_create_task(_close(desk))

    async def stop(_event):
        expire()

    sessions[address] = (
        desk,
        hass.loop.call_later(HANDOFF_TIMEOUT, expire),
        hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, stop),
    )


@callback
def take_session(hass: HomeAssistant, address: str) -> DeskClient | None:
    """Transfer ownership once; no connection or panel write is performed."""
    session = hass.data.get(_KEY, {}).pop(address, None)
    if session is None:
        return None
    desk, timer, unsubscribe = session
    timer.cancel()
    unsubscribe()
    return desk


async def _close(desk: DeskClient) -> None:
    await _drain_cleanup(asyncio.gather(desk.disconnect(), return_exceptions=True))
