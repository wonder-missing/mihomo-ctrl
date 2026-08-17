from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_API_URL = "http://127.0.0.1:9090"
_DEFAULT_GROUP = "PROXY"


@dataclass(frozen=True)
class Settings:
    api_url: str = _DEFAULT_API_URL
    secret: str = ""
    default_group: str = _DEFAULT_GROUP

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_url=_env("MIHOMO_API_URL", _DEFAULT_API_URL),
            secret=os.environ.get("MIHOMO_SECRET", ""),
            default_group=_env("MIHOMO_DEFAULT_GROUP", _DEFAULT_GROUP),
        )


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


settings = Settings.from_env()
