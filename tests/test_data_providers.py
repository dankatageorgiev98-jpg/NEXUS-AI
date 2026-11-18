from unittest.mock import Mock

import pytest

from core.market_data import MarketData
from core.new_gem_hunter import NewGemHunter
from core.provider_errors import ProviderError
from core.token_discovery import TokenDiscovery


class FakeResponse:
    def __init__(self, data=None, status_code=200, headers=None):
        self.data = data
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise __import__("requests").HTTPError(
                f"HTTP {self.status_code}"
            )

    def json(self):
        return self.data


def test_token_discovery_deduplicates_solana_addresses():
    discovery = TokenDiscovery()
    discovery.session.get = Mock(return_value=FakeResponse([
        {"chainId": "solana", "tokenAddress": "TokenA"},
        {"chainId": "solana", "tokenAddress": "TokenA"},
        {"chainId": "ethereum", "tokenAddress": "TokenB"},
    ]))

    tokens = discovery.get_latest_solana_tokens()

    assert [token["address"] for token in tokens] == ["TokenA"]


def test_token_discovery_retries_rate_limit(monkeypatch):
    discovery = TokenDiscovery()
    responses = [
        FakeResponse(status_code=429, headers={"Retry-After": "0"}),
        FakeResponse([{"chainId": "solana", "tokenAddress": "TokenA"}]),
    ]
    discovery.session.get = Mock(side_effect=responses)
    monkeypatch.setattr("core.token_discovery.time.sleep", lambda _: None)

    assert len(discovery.get_latest_solana_tokens()) == 1
    assert discovery.session.get.call_count == 2


def test_token_discovery_raises_provider_error_on_request_failure():
    import requests

    discovery = TokenDiscovery()
    discovery.session.get = Mock(
        side_effect=requests.Timeout("provider timed out")
    )

    with pytest.raises(ProviderError, match="request failed"):
        discovery.get_latest_solana_tokens()


def test_market_data_rejects_non_finite_numbers_and_deduplicates_pairs():
    provider = MarketData()
    pair = {
        "chainId": "solana",
        "pairAddress": "PairA",
        "baseToken": {"address": "TokenA"},
        "quoteToken": {},
        "volume": {"h24": "NaN"},
        "liquidity": {"usd": "Infinity"},
        "priceChange": {"h24": "-Infinity"},
        "txns": {"h24": {"buys": "NaN", "sells": 3}},
    }
    provider.session.get = Mock(
        return_value=FakeResponse([pair, dict(pair)])
    )

    results = provider.get_token_market_data("TokenA")

    assert len(results) == 1
    assert results[0]["volume_24h_usd"] is None
    assert results[0]["liquidity_usd"] is None
    assert results[0]["price_change_24h_percent"] is None
    assert results[0]["buys_24h"] is None
    assert results[0]["sells_24h"] == 3
    assert results[0]["retrieved_at"].tzinfo is not None


def test_market_data_api_failure_is_not_an_empty_result():
    import requests

    provider = MarketData()
    provider.session.get = Mock(
        side_effect=requests.ConnectionError("offline")
    )

    with pytest.raises(ProviderError, match="request failed"):
        provider.get_token_pairs("TokenA")


def test_market_data_retries_rate_limit(monkeypatch):
    provider = MarketData()
    provider.session.get = Mock(side_effect=[
        FakeResponse(status_code=429, headers={"Retry-After": "0"}),
        FakeResponse([]),
    ])
    monkeypatch.setattr("core.market_data.time.sleep", lambda _: None)

    assert provider.get_token_pairs("TokenA") == []
    assert provider.session.get.call_count == 2


def test_market_data_rejects_malformed_nested_pair():
    provider = MarketData()
    provider.session.get = Mock(return_value=FakeResponse([
        {
            "chainId": "solana",
            "pairAddress": "PairA",
            "baseToken": "invalid",
        },
    ]))

    with pytest.raises(ProviderError, match="Invalid market data field"):
        provider.get_token_market_data("TokenA")


def test_new_gem_hunter_shares_recent_scan_and_refetches_for_larger_limit():
    discovery = Mock()
    discovery.get_latest_solana_tokens.side_effect = [
        [{"address": "A"}],
        [{"address": "A"}, {"address": "B"}],
    ]
    market_data = Mock()
    market_data.get_token_market_data.return_value = []
    hunter = NewGemHunter(
        discovery=discovery,
        market_data=market_data,
        cache_ttl_seconds=30,
    )

    first = hunter.scan_latest_tokens(limit=1)
    second = hunter.scan_latest_tokens(limit=1)
    third = hunter.scan_latest_tokens(limit=2)

    assert len(first) == 1
    assert len(second) == 1
    assert len(third) == 2
    assert discovery.get_latest_solana_tokens.call_count == 2
