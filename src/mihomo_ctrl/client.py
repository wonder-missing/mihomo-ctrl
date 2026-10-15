from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from mihomo_ctrl.config import Settings, settings
from mihomo_ctrl.errors import MihomoAPIError, MihomoConnectionError, MihomoError

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 5.0

SYSTEM_BUILTINS = frozenset(
    {
        "GLOBAL",
        "DIRECT",
        "REJECT",
        "COMPATIBLE",
        "PASS",
        "PASS-RULE",
        "REJECT-DROP",
    }
)
NOISE_KEYWORDS = ("traffic", "expire", "remaining", "http://", "https://")


def is_noise_or_group(name: str, info: Mapping[str, Any] | None = None) -> bool:
    """系统内置、代理组、订阅流量/到期这类项，不要当成节点。"""
    if name in SYSTEM_BUILTINS:
        return True
    if info is not None and "all" in info:
        return True
    return any(keyword in name for keyword in NOISE_KEYWORDS)


def latest_delay(history: object) -> int | None:
    if not isinstance(history, list) or not history:
        return None
    last = history[-1]
    if not isinstance(last, Mapping):
        return None
    delay = last.get("delay")
    if isinstance(delay, int) and delay > 0:
        return delay
    return None


def delay_sort_key(item: tuple[str, str, int | None]) -> tuple[int, int | str]:
    name, _proxy_type, delay = item
    if delay is not None:
        return (0, delay)
    return (1, name)


def nodes_by_delay(nodes: tuple[str, ...], delays: dict[str, int]) -> list[str]:
    items = [(name, "", delays.get(name)) for name in nodes]
    items.sort(key=delay_sort_key)
    return [name for name, _, _ in items]


@dataclass(frozen=True)
class ProxyGroup:
    name: str
    proxy_type: str
    now: str
    nodes: tuple[str, ...]
    fixed: str | None = None


def _group_from_info(name: str, info: Mapping[str, Any]) -> ProxyGroup:
    raw_nodes = info.get("all", [])
    nodes = tuple(node for node in raw_nodes if isinstance(node, str))
    raw_fixed = info.get("fixed")
    fixed = raw_fixed if isinstance(raw_fixed, str) and raw_fixed else None
    return ProxyGroup(
        name=name,
        proxy_type=str(info.get("type", "Unknown")),
        now=str(info.get("now", "Unknown")),
        nodes=nodes,
        fixed=fixed,
    )


class MihomoClient:
    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or settings

    def close(self) -> None:
        return None

    def __enter__(self) -> MihomoClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def request(
        self, method: str, path: str, data: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self.config.api_url}{path}"
        headers: dict[str, str] = {}
        if self.config.secret:
            headers["Authorization"] = f"Bearer {self.config.secret}"
        body: bytes | None = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data, ensure_ascii=False).encode()

        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=HTTP_TIMEOUT) as response:
                status = getattr(response, "status", 200)
                raw = response.read()
        except HTTPError as exc:
            message = _error_from_http(exc)
            logger.error(
                "Mihomo API %s %s failed: HTTP %s %s",
                method,
                path,
                exc.code,
                message,
            )
            raise MihomoAPIError(exc.code, message) from exc
        except URLError as exc:
            logger.error("cannot reach Mihomo API %s: %s", url, exc)
            raise MihomoConnectionError(self.config.api_url, str(exc.reason)) from exc
        except (OSError, ValueError) as exc:
            logger.error("cannot reach Mihomo API %s: %s", url, exc)
            raise MihomoConnectionError(self.config.api_url, str(exc)) from exc

        if status == 204 or not raw:
            return {}
        try:
            return json.loads(raw.decode())
        except (ValueError, UnicodeError) as exc:
            logger.error(
                "Mihomo API %s %s returned invalid payload: %s",
                method,
                path,
                exc,
            )
            raise MihomoAPIError(
                status, f"Invalid JSON from Mihomo API (HTTP {status})"
            ) from exc

    def proxies(self) -> dict[str, Any]:
        payload = self.request("GET", "/proxies")
        raw = payload.get("proxies", {}) if isinstance(payload, dict) else {}
        return raw if isinstance(raw, dict) else {}

    def list_groups(self, proxies: dict[str, Any] | None = None) -> list[ProxyGroup]:
        data = self.proxies() if proxies is None else proxies
        groups: list[ProxyGroup] = []
        for name, info in data.items():
            if not isinstance(info, dict) or "all" not in info or name == "GLOBAL":
                continue
            groups.append(_group_from_info(name, info))
        return groups

    def get_group(self, name: str, proxies: dict[str, Any] | None = None) -> ProxyGroup:
        data = self.proxies() if proxies is None else proxies
        info = data.get(name)
        if not isinstance(info, dict) or "all" not in info:
            raise MihomoError(f"Proxy Group not found: {name}")
        return _group_from_info(name, info)

    def providers(self) -> dict[str, Any]:
        payload = self.request("GET", "/providers/proxies")
        raw = payload.get("providers", {}) if isinstance(payload, dict) else {}
        return raw if isinstance(raw, dict) else {}

    def delay_map(self) -> dict[str, int]:
        delays: dict[str, int] = {}
        try:
            for name, info in self.proxies().items():
                if not isinstance(info, dict):
                    continue
                delay = latest_delay(info.get("history"))
                if delay is not None:
                    delays[name] = delay
        except MihomoError:
            logger.debug("skip /proxies while building delay map", exc_info=True)

        try:
            for provider in self.providers().values():
                if not isinstance(provider, dict):
                    continue
                for node in provider.get("proxies", []):
                    if not isinstance(node, dict):
                        continue
                    node_name = node.get("name")
                    delay = latest_delay(node.get("history"))
                    if isinstance(node_name, str) and delay is not None:
                        delays[node_name] = delay
        except MihomoError:
            logger.debug("skip providers while building delay map", exc_info=True)

        return delays

    def leaf_proxies(self) -> list[tuple[str, str, int | None]]:
        """按延迟列出节点（独立代理，不含代理组）。"""
        delays = self.delay_map()
        found: dict[str, str] = {}

        last_error: MihomoError | None = None
        try:
            for provider in self.providers().values():
                if not isinstance(provider, dict):
                    continue
                for node in provider.get("proxies", []):
                    if not isinstance(node, dict):
                        continue
                    name = node.get("name")
                    if isinstance(name, str) and not is_noise_or_group(name):
                        found[name] = str(node.get("type", "Unknown"))
        except MihomoError as exc:
            last_error = exc
            logger.debug("skip providers while listing nodes", exc_info=True)

        try:
            for name, info in self.proxies().items():
                if not isinstance(info, dict) or is_noise_or_group(name, info):
                    continue
                found.setdefault(name, str(info.get("type", "Unknown")))
        except MihomoError as exc:
            last_error = exc
            logger.debug("skip /proxies while listing nodes", exc_info=True)

        if not found and last_error is not None:
            raise last_error

        items = [
            (name, proxy_type, delays.get(name)) for name, proxy_type in found.items()
        ]
        items.sort(key=delay_sort_key)
        return items

    def switch(self, group: str, node: str) -> None:
        encoded_group = quote(group, safe="")
        self.request("PUT", f"/proxies/{encoded_group}", {"name": node})
        logger.info("switched group %r to %r", group, node)

    def unpin(self, group: str) -> None:
        encoded_group = quote(group, safe="")
        self.request("DELETE", f"/proxies/{encoded_group}")
        logger.info("unpinned group %r", group)


def _error_from_http(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode())
    except (ValueError, UnicodeError):
        return f"API Request Failed (HTTP {exc.code})"
    if isinstance(payload, dict):
        message = payload.get("message")
        if message:
            return f"API Error (HTTP {exc.code}): {message}"
    return f"API Request Failed (HTTP {exc.code})"
