
import math
import time
from datetime import datetime, timezone

import requests

from core.activity_logger import ActivityLogger
from core.provider_errors import ProviderError


class MarketData:

    BASE_URL = "https://api.dexscreener.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "NEXUS-AI/1.0"
        })

    @staticmethod
    def _to_float(value):
        if isinstance(value, bool):
            return None
        try:
            result = float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
        return result if result is not None and math.isfinite(result) else None

    @staticmethod
    def _to_count(value):
        number = MarketData._to_float(value)
        if number is None or number < 0 or not number.is_integer():
            return None
        return int(number)

    def get_token_pairs(self, token_address):

        if not token_address:
            return []

        url = (
            f"{self.BASE_URL}/token-pairs/v1/solana/"
            f"{token_address}"
        )

        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=15)
                if response.status_code == 429 and attempt < 2:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(float(retry_after), 5.0)
                    except (TypeError, ValueError):
                        delay = 2 ** (attempt + 1)
                    time.sleep(max(delay, 0.0))
                    continue

                response.raise_for_status()
                data = response.json()
                break
            except requests.RequestException as error:
                ActivityLogger.error(
                    f"Market data request failed: {error}"
                )
                raise ProviderError(
                    f"Market data request failed: {error}"
                ) from error
            except ValueError as error:
                ActivityLogger.error(
                    f"Invalid market data response: {error}"
                )
                raise ProviderError(
                    f"Invalid market data response: {error}"
                ) from error
        else:
            raise ProviderError(
                "Market data request failed after HTTP 429 retries."
            )

        if not isinstance(data, list):
            raise ProviderError(
                "Unexpected market data response: expected a list."
            )

        pairs = []
        seen_pair_addresses = set()
        for pair in data:
            if not isinstance(pair, dict):
                raise ProviderError(
                    "Unexpected market data item: expected an object."
                )
            if pair.get("chainId") != "solana":
                continue

            pair_address = pair.get("pairAddress")
            if not isinstance(pair_address, str) or not pair_address:
                continue
            if pair_address in seen_pair_addresses:
                continue

            seen_pair_addresses.add(pair_address)
            pairs.append(pair)
        return pairs

    def get_token_market_data(self, token_address):

        pairs = self.get_token_pairs(token_address)
        market_data = []
        retrieved_at = datetime.now(timezone.utc)

        for pair in pairs:

            nested_fields = (
                "baseToken",
                "quoteToken",
                "volume",
                "liquidity",
                "priceChange",
                "txns",
            )
            for field in nested_fields:
                if pair.get(field) is not None and not isinstance(
                    pair[field], dict
                ):
                    raise ProviderError(
                        f"Invalid market data field: {field}"
                    )

            base_token = pair.get("baseToken") or {}
            quote_token = pair.get("quoteToken") or {}
            volume = pair.get("volume") or {}
            liquidity = pair.get("liquidity") or {}
            price_change = pair.get("priceChange") or {}
            transactions = pair.get("txns") or {}
            if (
                transactions.get("h24") is not None
                and not isinstance(transactions["h24"], dict)
            ):
                raise ProviderError(
                    "Invalid market data field: txns.h24"
                )
            transactions_24h = transactions.get("h24") or {}

            market_data.append({

                "token_name": base_token.get("name"),
                "token_symbol": base_token.get("symbol"),
                "token_address": base_token.get("address"),

                "quote_token": quote_token.get("symbol"),

                "price_usd": self._to_float(
                    pair.get("priceUsd")
                ),

                "volume_24h_usd": self._to_float(
                    volume.get("h24")
                ),

                "liquidity_usd": self._to_float(
                    liquidity.get("usd")
                ),

                "market_cap_usd": self._to_float(
                    pair.get("marketCap")
                ),

                "fdv_usd": self._to_float(
                    pair.get("fdv")
                ),

                "price_change_24h_percent": self._to_float(
                    price_change.get("h24")
                ),

                "buys_24h": self._to_count(
                    transactions_24h.get("buys")
                ),
                "sells_24h": self._to_count(
                    transactions_24h.get("sells")
                ),

                "dex": pair.get("dexId"),
                "pair_address": pair.get("pairAddress"),
                "pair_url": pair.get("url"),

                "pair_created_at": pair.get("pairCreatedAt"),
                "data_source": "DexScreener",
                "retrieved_at": retrieved_at,

            })

        ActivityLogger.info(
            f"Processed {len(market_data)} market pairs "
            f"for {token_address}."
        )

        return market_data

