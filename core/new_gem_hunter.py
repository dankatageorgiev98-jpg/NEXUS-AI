
import copy
import threading
import time

from core.token_discovery import TokenDiscovery
from core.market_data import MarketData
from core.activity_logger import ActivityLogger


class NewGemHunter:

    def __init__(
        self,
        discovery=None,
        market_data=None,
        cache_ttl_seconds=5.0,
    ):
        self.discovery = discovery or TokenDiscovery()
        self.market_data = market_data or MarketData()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._scan_lock = threading.Lock()
        self._cached_scan = None
        self._cached_scan_at = 0.0
        self._cached_limit = 0

    def scan_latest_tokens(self, limit=5):
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if self.cache_ttl_seconds < 0:
            raise ValueError("cache_ttl_seconds cannot be negative")

        with self._scan_lock:
            now = time.monotonic()
            if (
                self._cached_scan is not None
                and self._cached_limit >= limit
                and now - self._cached_scan_at < self.cache_ttl_seconds
            ):
                return copy.deepcopy(self._cached_scan[:limit])

            tokens = self.discovery.get_latest_solana_tokens()

            results = []

            for token in tokens[:limit]:
                address = token["address"]

                market_info = self.market_data.get_token_market_data(
                    address
                )

                results.append({
                    "address": address,
                    "description": token.get("description"),
                    "url": token.get("url"),
                    "market_data": market_info
                })

                ActivityLogger.info(
                    f"NEW GEM HUNTER analyzed token: {address}"
                )

            ActivityLogger.info(
                f"NEW GEM HUNTER completed scan. "
                f"Analyzed {len(results)} tokens."
            )

            self._cached_scan = copy.deepcopy(results)
            self._cached_scan_at = time.monotonic()
            self._cached_limit = limit
            return results
