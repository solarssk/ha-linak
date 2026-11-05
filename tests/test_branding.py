"""Verify shipped PNGs through HA's real brand handlers without HTTP sockets."""

from collections import deque
from pathlib import Path
import struct
from unittest.mock import AsyncMock, patch
import zlib

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
import pytest

from homeassistant.components.brands import (
    BrandsIntegrationView,
    BrandsMarketplaceView,
    _read_brand_file,
)
from homeassistant.components.http import KEY_AUTHENTICATED
from homeassistant.loader import async_get_custom_components

BRAND = Path(__file__).resolve().parents[1] / "custom_components/ha_linak/brand"
SIZES = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
    "logo.png": (1204, 256),
    "logo@2x.png": (2408, 512),
}
IMAGES = {name: name for name in SIZES} | {f"dark_{name}": name for name in SIZES}
VIEWS = (BrandsIntegrationView, BrandsMarketplaceView)


@pytest.mark.parametrize("name,size", SIZES.items())
def test_shipped_png_contract(name, size):
    data = (BRAND / name).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    compressed = b""
    chunks = []
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        checksum = struct.unpack_from(">I", data, offset + 8 + length)[0]
        assert zlib.crc32(kind + payload) == checksum
        if kind == b"IHDR":
            assert struct.unpack_from(">II", payload) == size
        if kind == b"IDAT":
            compressed += payload
        chunks.append(kind)
        offset += length + 12
    assert offset == len(data)
    assert chunks[0] == b"IHDR"
    assert chunks[-1] == b"IEND"
    assert zlib.decompress(compressed)


@pytest.mark.parametrize("view_type", VIEWS)
@pytest.mark.parametrize("image,source", IMAGES.items())
@pytest.mark.parametrize("placeholder", ["", "?placeholder=no"])
@pytest.mark.parametrize("auth", ["session", "query"])
async def test_local_brand_handlers(hass, view_type, image, source, placeholder, auth):
    integrations = await async_get_custom_components(hass)
    integration = integrations["ha_linak"]
    assert integration.has_branding
    assert Path(integration.file_path).resolve() / "brand" == BRAND
    hass.data["brands"] = deque(["test-brand-token"], maxlen=2)
    route = "integration" if view_type is BrandsIntegrationView else "marketplace"
    view = view_type(hass)
    assert view.url == f"/api/brands/{route}/{{domain}}/{{image}}"
    url = f"/api/brands/{route}/ha_linak/{image}{placeholder}"
    if auth == "query":
        url += ("&" if placeholder else "?") + "token=test-brand-token"
    request = make_mocked_request("GET", url)
    request[KEY_AUTHENTICATED] = auth == "session"
    with (
        patch(
            "homeassistant.components.brands._BrandsBaseView._get_image_data",
            new_callable=AsyncMock,
            side_effect=AssertionError("Local branding must not use cache or CDN"),
        ) as cdn,
        patch(
            "homeassistant.components.brands._BrandsBaseView._serve_placeholder",
            new_callable=AsyncMock,
            side_effect=AssertionError("Local branding must not use a placeholder"),
        ) as fallback,
    ):
        response = await view.get(request, "ha_linak", image)
        assert response.status == 200
        assert response.content_type == "image/png"
        assert response.body == (BRAND / source).read_bytes()
        cdn.assert_not_awaited()
        fallback.assert_not_awaited()


@pytest.mark.parametrize("view_type", VIEWS)
async def test_brand_handler_requires_authentication(hass, view_type):
    hass.data["brands"] = deque(["test-brand-token"], maxlen=2)
    request = make_mocked_request("GET", "/?placeholder=no")
    request[KEY_AUTHENTICATED] = False
    with pytest.raises(web.HTTPForbidden):
        await view_type(hass).get(request, "ha_linak", "icon.png")


@pytest.mark.parametrize("image", IMAGES)
@pytest.mark.parametrize("available", [("icon.png",), ("icon.png", "logo.png")])
def test_missing_high_resolution_and_dark_files_use_real_fallbacks(
    tmp_path, image, available
):
    for name in available:
        (tmp_path / name).write_bytes((BRAND / name).read_bytes())
    source = "logo.png" if "logo" in image and "logo.png" in available else "icon.png"
    assert _read_brand_file(tmp_path, image) == (BRAND / source).read_bytes()
