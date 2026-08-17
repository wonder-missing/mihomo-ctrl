from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.client import HTTPMessage
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request

from mihomo_ctrl.client import (
    MihomoClient,
    delay_sort_key,
    is_noise_or_group,
    latest_delay,
    nodes_by_delay,
)
from mihomo_ctrl.config import Settings
from mihomo_ctrl.errors import MihomoAPIError, MihomoConnectionError, MihomoError


def test_system_builtin_is_noise() -> None:
    assert is_noise_or_group("DIRECT") is True
    assert is_noise_or_group("REJECT-DROP") is True


def test_group_with_all_is_noise() -> None:
    assert is_noise_or_group("美国", {"all": ["a", "b"], "type": "Selector"}) is True


def test_subscription_banner_is_noise() -> None:
    assert is_noise_or_group("剩余流量: 12GB traffic") is True
    assert is_noise_or_group("expire: 2026-12-01") is True
    assert is_noise_or_group("https://example.com/sub") is True


def test_leaf_node_is_not_noise() -> None:
    assert is_noise_or_group("美国LA-优化-GPT", {"type": "ss"}) is False


def test_latest_delay_uses_last_positive() -> None:
    assert latest_delay([{"delay": 10}, {"delay": 88}]) == 88


def test_latest_delay_ignores_zero_and_empty() -> None:
    assert latest_delay([]) is None
    assert latest_delay(None) is None
    assert latest_delay([{"delay": 0}]) is None


def test_delay_sort_puts_timed_nodes_first() -> None:
    items = [
        ("slow", "ss", 200),
        ("untimed", "vmess", None),
        ("fast", "ss", 20),
    ]
    items.sort(key=delay_sort_key)
    assert [name for name, _, _ in items] == ["fast", "slow", "untimed"]


def test_nodes_by_delay_orders_timed_first() -> None:
    nodes = ("slow", "none", "fast")
    delays = {"slow": 200, "fast": 20}
    assert nodes_by_delay(nodes, delays) == ["fast", "slow", "none"]


class _FakeResponse:
    def __init__(self, status: int, payload: object | None = None) -> None:
        self.status = status
        self._raw = b"" if payload is None else json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _client() -> MihomoClient:
    return MihomoClient(Settings(api_url="http://127.0.0.1:9090", secret="s3cret"))


@contextmanager
def _patch_urlopen(handler: Callable[..., object]) -> Iterator[None]:
    with patch("mihomo_ctrl.client.urlopen", side_effect=handler):
        yield


def test_request_sends_bearer_and_parses_json() -> None:
    def handler(request: Request, timeout: float | None = None) -> _FakeResponse:
        assert timeout == 5.0
        assert request.get_header("Authorization") == "Bearer s3cret"
        assert request.full_url.endswith("/proxies")
        return _FakeResponse(200, {"proxies": {"PROXY": {"all": ["a"]}}})

    with _patch_urlopen(handler), _client() as client:
        assert client.proxies()["PROXY"]["all"] == ["a"]


def test_request_204_returns_empty_dict() -> None:
    def handler(_request: Request, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(204)

    with _patch_urlopen(handler), _client() as client:
        assert client.request("PUT", "/proxies/PROXY", {"name": "美国"}) == {}


def test_request_http_error_uses_api_message() -> None:
    def handler(_request: Request, timeout: float | None = None) -> _FakeResponse:
        raise HTTPError(
            "http://127.0.0.1:9090/proxies",
            400,
            "Bad Request",
            HTTPMessage(),
            BytesIO(b'{"message":"proxy not found"}'),
        )

    try:
        with _patch_urlopen(handler), _client() as client:
            client.request("GET", "/proxies")
    except MihomoAPIError as exc:
        assert exc.status == 400
        assert "proxy not found" in str(exc)
    else:
        raise AssertionError("expected MihomoAPIError")


def test_request_connection_error() -> None:
    def handler(_request: Request, timeout: float | None = None) -> _FakeResponse:
        raise URLError("boom")

    try:
        with _patch_urlopen(handler), _client() as client:
            client.request("GET", "/proxies")
    except MihomoConnectionError as exc:
        assert "127.0.0.1:9090" in str(exc)
    else:
        raise AssertionError("expected MihomoConnectionError")


def test_request_non_json_body_is_api_error() -> None:
    def handler(_request: Request, timeout: float | None = None) -> _FakeResponse:
        response = _FakeResponse(200)
        response._raw = b"<html>not json</html>"
        return response

    try:
        with _patch_urlopen(handler), _client() as client:
            client.request("GET", "/proxies")
    except MihomoAPIError as exc:
        assert exc.status == 200
        assert "Invalid JSON" in str(exc)
    else:
        raise AssertionError("expected MihomoAPIError")


def test_request_timeout_is_connection_error() -> None:
    def handler(_request: Request, timeout: float | None = None) -> _FakeResponse:
        raise TimeoutError("timed out")

    try:
        with _patch_urlopen(handler), _client() as client:
            client.request("GET", "/proxies")
    except MihomoConnectionError as exc:
        assert "127.0.0.1:9090" in str(exc)
    else:
        raise AssertionError("expected MihomoConnectionError")


def test_request_scheme_less_url_is_connection_error() -> None:
    client = MihomoClient(Settings(api_url="127.0.0.1:9090", secret=""))
    try:
        client.request("GET", "/proxies")
    except MihomoConnectionError as exc:
        assert "127.0.0.1:9090" in str(exc)
    else:
        raise AssertionError("expected MihomoConnectionError")


def test_list_groups_skips_global_and_leaves() -> None:
    def handler(request: Request, timeout: float | None = None) -> _FakeResponse:
        assert request.full_url.endswith("/proxies")
        return _FakeResponse(
            200,
            {
                "proxies": {
                    "GLOBAL": {
                        "all": ["默认"],
                        "type": "Selector",
                        "now": "默认",
                    },
                    "默认": {
                        "all": ["美国", "直连"],
                        "type": "Selector",
                        "now": "美国",
                    },
                    "直连": {"type": "Direct"},
                }
            },
        )

    with _patch_urlopen(handler), _client() as client:
        groups = client.list_groups()
    assert [group.name for group in groups] == ["默认"]
    assert groups[0].now == "美国"
    assert groups[0].nodes == ("美国", "直连")
    assert groups[0].fixed is None


def test_get_group_missing_raises() -> None:
    def handler(_request: Request, timeout: float | None = None) -> _FakeResponse:
        payload = {"proxies": {"默认": {"all": ["美国"], "now": "美国"}}}
        return _FakeResponse(200, payload)

    try:
        with _patch_urlopen(handler), _client() as client:
            client.get_group("没有这个组")
    except MihomoError as exc:
        assert "没有这个组" in str(exc)
    else:
        raise AssertionError("expected MihomoError")


def test_leaf_proxies_filters_and_sorts() -> None:
    def handler(request: Request, timeout: float | None = None) -> _FakeResponse:
        if request.full_url.endswith("/providers/proxies"):
            return _FakeResponse(
                200,
                {
                    "providers": {
                        "sub": {
                            "proxies": [
                                {
                                    "name": "fast",
                                    "type": "ss",
                                    "history": [{"delay": 12}],
                                },
                                {
                                    "name": "expire: tomorrow",
                                    "type": "ss",
                                    "history": [{"delay": 1}],
                                },
                            ]
                        }
                    }
                },
            )
        return _FakeResponse(
            200,
            {
                "proxies": {
                    "PROXY": {"all": ["fast"], "type": "Selector", "now": "fast"},
                    "DIRECT": {"type": "Direct"},
                    "slow": {"type": "vmess", "history": [{"delay": 90}]},
                }
            },
        )

    with _patch_urlopen(handler), _client() as client:
        items = client.leaf_proxies()
    assert items == [("fast", "ss", 12), ("slow", "vmess", 90)]


def test_leaf_proxies_raises_when_api_unreachable() -> None:
    def handler(_request: Request, timeout: float | None = None) -> _FakeResponse:
        raise URLError("boom")

    try:
        with _patch_urlopen(handler), _client() as client:
            client.leaf_proxies()
    except MihomoConnectionError:
        pass
    else:
        raise AssertionError("expected MihomoConnectionError")


def test_list_groups_reads_fixed() -> None:
    def handler(_request: Request, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(
            200,
            {
                "proxies": {
                    "自动选择": {
                        "all": ["HK-01", "US-01"],
                        "type": "URLTest",
                        "now": "HK-01",
                        "fixed": "HK-01",
                    }
                }
            },
        )

    with _patch_urlopen(handler), _client() as client:
        groups = client.list_groups()
    assert groups[0].fixed == "HK-01"


def test_switch_encodes_group_name() -> None:
    seen: list[Request] = []

    def handler(request: Request, timeout: float | None = None) -> _FakeResponse:
        seen.append(request)
        return _FakeResponse(204)

    with _patch_urlopen(handler), _client() as client:
        client.switch("默认", "美国")

    assert len(seen) == 1
    request = seen[0]
    assert request.get_method() == "PUT"
    assert "%E9%BB%98%E8%AE%A4" in request.full_url
    body = request.data
    assert isinstance(body, bytes)
    assert b'"name"' in body
    assert "美国".encode() in body


def test_unpin_sends_delete() -> None:
    seen: list[Request] = []

    def handler(request: Request, timeout: float | None = None) -> _FakeResponse:
        seen.append(request)
        return _FakeResponse(204)

    with _patch_urlopen(handler), _client() as client:
        client.unpin("自动选择")

    assert len(seen) == 1
    request = seen[0]
    assert request.get_method() == "DELETE"
    assert quote("自动选择", safe="") in request.full_url
    assert request.data is None
