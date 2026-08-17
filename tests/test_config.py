from pytest import MonkeyPatch

from mihomo_ctrl.config import Settings


def test_from_env_reads_prefix(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("MIHOMO_API_URL", "http://10.0.0.2:9090")
    monkeypatch.setenv("MIHOMO_SECRET", "abc")
    monkeypatch.setenv("MIHOMO_DEFAULT_GROUP", "默认")
    loaded = Settings.from_env()
    assert loaded.api_url == "http://10.0.0.2:9090"
    assert loaded.secret == "abc"
    assert loaded.default_group == "默认"


def test_from_env_empty_url_falls_back(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("MIHOMO_API_URL", "")
    monkeypatch.delenv("MIHOMO_DEFAULT_GROUP", raising=False)
    loaded = Settings.from_env()
    assert loaded.api_url == "http://127.0.0.1:9090"
    assert loaded.default_group == "PROXY"
