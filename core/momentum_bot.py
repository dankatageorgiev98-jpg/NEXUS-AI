
import math

from core.new_gem_hunter import NewGemHunter
from core.activity_logger import ActivityLogger


class MomentumBot:

    def __init__(self, gem_hunter=None):
        self.gem_hunter = gem_hunter or NewGemHunter()

    @staticmethod
    def classify_momentum(price_change):
        try:
            price_change = float(price_change)
        except (TypeError, ValueError, OverflowError):
            return "UNKNOWN"

        if not math.isfinite(price_change):
            return "UNKNOWN"

        if price_change >= 20:
            return "STRONG_UP"

        if price_change >= 5:
            return "UP"

        if price_change <= -20:
            return "STRONG_DOWN"

        if price_change <= -5:
            return "DOWN"

        return "NEUTRAL"

    def analyze_latest_tokens(self, limit=5):

        tokens = self.gem_hunter.scan_latest_tokens(
            limit=limit
        )

        reports = []

        for token in tokens:

            for pair in token["market_data"]:

                price_change = pair.get(
                    "price_change_24h_percent"
                )

                momentum = self.classify_momentum(
                    price_change
                )

                report = {
                    "token_address": token["address"],
                    "token_symbol": pair.get("token_symbol"),
                    "price_usd": pair.get("price_usd"),
                    "price_change_24h_percent": price_change,
                    "volume_24h_usd": pair.get("volume_24h_usd"),
                    "buys_24h": pair.get("buys_24h"),
                    "sells_24h": pair.get("sells_24h"),
                    "momentum": momentum,
                    "pair_url": pair.get("pair_url")
                }

                reports.append(report)

        ActivityLogger.info(
            f"MOMENTUM BOT analyzed {len(reports)} market pairs."
        )

        return reports
