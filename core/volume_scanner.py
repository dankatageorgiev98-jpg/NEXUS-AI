
from core.new_gem_hunter import NewGemHunter
from core.activity_logger import ActivityLogger


class VolumeScanner:

    def __init__(self, gem_hunter=None):
        self.gem_hunter = gem_hunter or NewGemHunter()

    def analyze_latest_tokens(self, limit=5):

        tokens = self.gem_hunter.scan_latest_tokens(
            limit=limit
        )

        reports = []

        for token in tokens:

            for pair in token["market_data"]:

                volume = pair.get("volume_24h_usd")
                liquidity = pair.get("liquidity_usd")
                buys = pair.get("buys_24h")
                sells = pair.get("sells_24h")

                buy_percentage = None

                if (
                    buys is not None
                    and sells is not None
                    and buys + sells > 0
                ):
                    total_transactions = buys + sells
                    buy_percentage = (
                        buys / total_transactions
                    ) * 100

                volume_liquidity_ratio = None

                if (
                    volume is not None
                    and liquidity is not None
                    and liquidity > 0
                ):
                    volume_liquidity_ratio = (
                        volume / liquidity
                    )

                report = {
                    "token_address": token["address"],
                    "token_symbol": pair.get("token_symbol"),
                    "price_usd": pair.get("price_usd"),
                    "volume_24h_usd": volume,
                    "liquidity_usd": liquidity,
                    "buys_24h": buys,
                    "sells_24h": sells,
                    "buy_percentage": buy_percentage,
                    "volume_liquidity_ratio": (
                        volume_liquidity_ratio
                    ),
                    "price_change_24h_percent": (
                        pair.get("price_change_24h_percent")
                    ),
                    "pair_url": pair.get("pair_url")
                }

                reports.append(report)

        ActivityLogger.info(
            f"VOLUME SCANNER analyzed "
            f"{len(reports)} market pairs."
        )

        return reports
