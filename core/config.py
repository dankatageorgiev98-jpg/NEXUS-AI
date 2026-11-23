import os
import warnings
from dataclasses import dataclass
from typing import Mapping


DEFAULT_SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"


@dataclass(frozen=True)
class RpcConfig:
    primary_url: str
    fallback_url: str | None = None

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> "RpcConfig":
        source = os.environ if environ is None else environ

        primary_value = source.get("NEXUS_SOLANA_RPC_URL")
        fallback_value = source.get("NEXUS_SOLANA_RPC_FALLBACK_URL")

        primary_url = (
            primary_value.strip()
            if isinstance(primary_value, str) and primary_value.strip()
            else DEFAULT_SOLANA_RPC_URL
        )
        fallback_url = (
            fallback_value.strip()
            if isinstance(fallback_value, str) and fallback_value.strip()
            else None
        )

        if (
            fallback_url is not None
            and fallback_url == primary_url
        ):
            warnings.warn(
                "NEXUS_SOLANA_RPC_FALLBACK_URL matches "
                "NEXUS_SOLANA_RPC_URL; duplicate fallback disabled.",
                RuntimeWarning,
                stacklevel=2,
            )
            fallback_url = None

        return cls(
            primary_url=primary_url,
            fallback_url=fallback_url,
        )
