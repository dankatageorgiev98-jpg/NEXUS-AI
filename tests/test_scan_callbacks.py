import pytest

from core import scan_callbacks
from core.provider_errors import ProviderError


def test_callbacks_connect_four_implemented_bots(monkeypatch):
    tokens = [
        {
            "address": "TokenA",
            "market_data": [{"liquidity_usd": 20000}],
        },
        {
            "address": "TokenB",
            "market_data": [{"liquidity_usd": 30000}],
        },
    ]

    class FakeGemHunter:
        def scan_latest_tokens(self):
            return tokens

    class FakeMomentumBot:
        def __init__(self, gem_hunter):
            self.gem_hunter = gem_hunter

        def analyze_latest_tokens(self):
            return ["momentum"]

    class FakeVolumeScanner:
        def __init__(self, gem_hunter):
            self.gem_hunter = gem_hunter

        def analyze_latest_tokens(self):
            return ["volume"]

    class FakeSafetyBot:
        def check_token(self, address, market_data):
            return {"token_address": address, "market_data": market_data}

    monkeypatch.setattr(scan_callbacks, "NewGemHunter", FakeGemHunter)
    monkeypatch.setattr(scan_callbacks, "MomentumBot", FakeMomentumBot)
    monkeypatch.setattr(scan_callbacks, "VolumeScanner", FakeVolumeScanner)
    monkeypatch.setattr(scan_callbacks, "SafetyBot", FakeSafetyBot)

    callbacks = scan_callbacks.create_scan_functions()

    assert set(callbacks) == {
        "NEW GEM HUNTER",
        "MOMENTUM BOT",
        "VOLUME SCANNER",
        "SAFETY BOT",
    }
    assert callbacks["NEW GEM HUNTER"]() == tokens
    assert callbacks["MOMENTUM BOT"]() == ["momentum"]
    assert callbacks["VOLUME SCANNER"]() == ["volume"]
    assert callbacks["SAFETY BOT"]() == [
        {
            "token_address": "TokenA",
            "market_data": [{"liquidity_usd": 20000}],
        },
    ]
    assert callbacks["SAFETY BOT"]() == [
        {
            "token_address": "TokenB",
            "market_data": [{"liquidity_usd": 30000}],
        },
    ]


def test_safety_callback_stops_batch_when_rpc_verification_fails(monkeypatch):
    checked_addresses = []

    class FakeGemHunter:
        def scan_latest_tokens(self):
            return [
                {"address": "TokenA", "market_data": []},
                {"address": "TokenB", "market_data": []},
            ]

    class FakeMomentumBot:
        def __init__(self, gem_hunter):
            pass

        def analyze_latest_tokens(self):
            return []

    class FakeVolumeScanner:
        def __init__(self, gem_hunter):
            pass

        def analyze_latest_tokens(self):
            return []

    class FakeSafetyBot:
        def check_token(self, address, market_data):
            checked_addresses.append(address)
            return {
                "checks": {"on_chain_verification": "FAILED"},
                "risks": ["RPC unavailable"],
            }

    monkeypatch.setattr(scan_callbacks, "NewGemHunter", FakeGemHunter)
    monkeypatch.setattr(scan_callbacks, "MomentumBot", FakeMomentumBot)
    monkeypatch.setattr(scan_callbacks, "VolumeScanner", FakeVolumeScanner)
    monkeypatch.setattr(scan_callbacks, "SafetyBot", FakeSafetyBot)

    callback = scan_callbacks.create_scan_functions()["SAFETY BOT"]

    with pytest.raises(ProviderError, match="Safety verification failed"):
        callback()
    assert checked_addresses == ["TokenA"]
