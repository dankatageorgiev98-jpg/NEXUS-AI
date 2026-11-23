import pytest

from core.config import DEFAULT_SOLANA_RPC_URL, RpcConfig


def test_default_primary_url():
    config = RpcConfig.load({})

    assert config.primary_url == DEFAULT_SOLANA_RPC_URL
    assert config.primary_url == "https://api.mainnet-beta.solana.com"


def test_configured_primary_url_overrides_default():
    config = RpcConfig.load({
        "NEXUS_SOLANA_RPC_URL": "https://primary.example",
    })

    assert config.primary_url == "https://primary.example"


def test_configured_fallback_url_is_loaded():
    config = RpcConfig.load({
        "NEXUS_SOLANA_RPC_FALLBACK_URL": "https://fallback.example",
    })

    assert config.fallback_url == "https://fallback.example"


def test_missing_fallback_remains_none():
    config = RpcConfig.load({})

    assert config.fallback_url is None


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_empty_primary_and_fallback_values_are_unset(value):
    config = RpcConfig.load({
        "NEXUS_SOLANA_RPC_URL": value,
        "NEXUS_SOLANA_RPC_FALLBACK_URL": value,
    })

    assert config.primary_url == DEFAULT_SOLANA_RPC_URL
    assert config.fallback_url is None


def test_leading_and_trailing_whitespace_is_stripped():
    config = RpcConfig.load({
        "NEXUS_SOLANA_RPC_URL": "  https://primary.example  ",
        "NEXUS_SOLANA_RPC_FALLBACK_URL": "  https://fallback.example  ",
    })

    assert config.primary_url == "https://primary.example"
    assert config.fallback_url == "https://fallback.example"


def test_identical_normalized_urls_warn_and_disable_fallback():
    with pytest.warns(
        RuntimeWarning,
        match="duplicate fallback disabled",
    ):
        config = RpcConfig.load({
            "NEXUS_SOLANA_RPC_URL": " https://same.example ",
            "NEXUS_SOLANA_RPC_FALLBACK_URL":
                "https://same.example ",
        })

    assert config.primary_url == "https://same.example"
    assert config.fallback_url is None


def test_different_primary_and_fallback_urls_are_preserved():
    config = RpcConfig.load({
        "NEXUS_SOLANA_RPC_URL": "https://primary.example",
        "NEXUS_SOLANA_RPC_FALLBACK_URL": "https://fallback.example",
    })

    assert config.primary_url == "https://primary.example"
    assert config.fallback_url == "https://fallback.example"


def test_custom_mapping_is_supported():
    environ = {
        "NEXUS_SOLANA_RPC_URL": "https://custom-primary.example",
        "NEXUS_SOLANA_RPC_FALLBACK_URL": "https://custom-fallback.example",
    }

    config = RpcConfig.load(environ)

    assert config.primary_url == "https://custom-primary.example"
    assert config.fallback_url == "https://custom-fallback.example"


def test_load_reads_environment_changes_without_cache(monkeypatch):
    monkeypatch.setenv(
        "NEXUS_SOLANA_RPC_URL",
        "https://first.example",
    )
    first = RpcConfig.load()

    monkeypatch.setenv(
        "NEXUS_SOLANA_RPC_URL",
        "https://second.example",
    )
    monkeypatch.setenv(
        "NEXUS_SOLANA_RPC_FALLBACK_URL",
        "https://fallback.example",
    )
    second = RpcConfig.load()

    assert first.primary_url == "https://first.example"
    assert first.fallback_url is None
    assert second.primary_url == "https://second.example"
    assert second.fallback_url == "https://fallback.example"
