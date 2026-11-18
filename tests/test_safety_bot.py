import requests
import pytest
from unittest.mock import Mock

from core.safety_bot import SafetyBot


def make_rpc_response(method):
    if method == "getAccountInfo":
        return {
            "value": {
                "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                "data": {
                    "parsed": {
                        "type": "mint",
                        "info": {
                            "mintAuthority": None,
                            "freezeAuthority": None,
                        },
                    },
                },
            },
        }
    if method == "getTokenSupply":
        return {"value": {"uiAmount": 1000}}
    if method == "getTokenLargestAccounts":
        return {
            "value": [
                {"address": f"account-{index}", "uiAmount": 50}
                for index in range(10)
            ] + [
                {"address": f"account-{index}", "uiAmount": 1}
                for index in range(10, 20)
            ],
        }
    if method == "getMultipleAccounts":
        return {
            "value": [
                {
                    "data": {
                        "parsed": {
                            "info": {
                                "owner": (
                                    "holder-0"
                                    if index < 2 else f"holder-{index}"
                                ),
                            },
                        },
                    },
                }
                for index in range(20)
            ],
        }
    raise AssertionError(f"Unexpected RPC method: {method}")


def test_concentration_uses_only_top_ten_token_accounts(monkeypatch):
    bot = SafetyBot()
    monkeypatch.setattr(
        bot,
        "_rpc_request",
        lambda method, params: make_rpc_response(method),
    )

    result = bot.check_token(
        "TokenA",
        market_data=[{"liquidity_usd": 20000}],
    )

    assert result["checks"]["top10_account_concentration"] == 50
    assert result["checks"][
        "top10_owner_concentration_observed"
    ] == pytest.approx(50.1)
    assert result["checks"]["owner_concentration_complete"] is False
    assert any("not verified independent owners" in warning
               for warning in result["warnings"])


def test_non_finite_supply_fails_closed(monkeypatch):
    bot = SafetyBot()

    def rpc_response(method, params):
        result = make_rpc_response(method)
        if method == "getTokenSupply":
            result["value"]["uiAmount"] = float("nan")
        return result

    monkeypatch.setattr(bot, "_rpc_request", rpc_response)

    result = bot.check_token(
        "TokenA",
        market_data=[{"liquidity_usd": 20000}],
    )

    assert result["status"] == "BLOCKED"
    assert any("Invalid token supply" in risk for risk in result["risks"])


def test_missing_market_data_fails_closed(monkeypatch):
    bot = SafetyBot()
    monkeypatch.setattr(
        bot,
        "_rpc_request",
        lambda method, params: make_rpc_response(method),
    )

    result = bot.check_token("TokenA", market_data=[])

    assert result["status"] == "BLOCKED"
    assert "Liquidity could not be verified" in result["risks"]


def test_rpc_uses_configured_fallback_after_primary_failure(monkeypatch):
    bot = SafetyBot()
    bot.RPC_URL = "https://primary.invalid"
    bot.RPC_FALLBACK_URL = "https://fallback.invalid"
    response = type(
        "Response",
        (),
        {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"result": {"value": "ok"}},
        },
    )()
    def post(endpoint, **kwargs):
        if endpoint == bot.RPC_URL:
            raise requests.Timeout()
        return response

    bot.session.post = Mock(side_effect=post)
    monkeypatch.setattr("core.safety_bot.time.sleep", lambda _: None)

    assert bot._rpc_request("getHealth", []) == {"value": "ok"}


def test_rpc_respects_retry_after_for_rate_limits(monkeypatch):
    bot = SafetyBot()
    bot.MIN_RPC_REQUEST_INTERVAL_SECONDS = 0
    retry_error = requests.HTTPError("429 Too Many Requests")
    retry_error.response = Mock(status_code=429)
    rate_limited = Mock(
        status_code=429,
        headers={"Retry-After": "0"},
    )
    rate_limited.raise_for_status.side_effect = retry_error
    success = Mock(
        status_code=200,
        json=Mock(return_value={"result": "ok"}),
    )
    success.raise_for_status.return_value = None
    bot.session.post = Mock(side_effect=[rate_limited, success])
    delays = []
    monkeypatch.setattr(
        "core.safety_bot.time.sleep",
        lambda delay: delays.append(delay),
    )

    assert bot._rpc_request("getHealth", []) == "ok"
    assert delays == [1.0]
