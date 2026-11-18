
import time

import requests

from core.activity_logger import ActivityLogger
from core.provider_errors import ProviderError


class TokenDiscovery:

    BASE_URL = "https://api.dexscreener.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "NEXUS-AI/1.0"
        })

    def get_latest_solana_tokens(self):
        url = f"{self.BASE_URL}/token-profiles/latest/v1"

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
                    f"Token discovery request failed: {error}"
                )
                raise ProviderError(
                    f"Token discovery request failed: {error}"
                ) from error
            except ValueError as error:
                ActivityLogger.error(
                    f"Invalid token discovery response: {error}"
                )
                raise ProviderError(
                    f"Invalid token discovery response: {error}"
                ) from error
        else:
            raise ProviderError(
                "Token discovery failed after HTTP 429 retries."
            )

        if not isinstance(data, list):
            raise ProviderError(
                "Unexpected token discovery response: expected a list."
            )

        solana_tokens = []
        seen_addresses = set()

        for token in data:
            if not isinstance(token, dict):
                raise ProviderError(
                    "Unexpected token discovery item: expected an object."
                )
            if token.get("chainId") != "solana":
                continue

            address = token.get("tokenAddress")
            if not isinstance(address, str) or not address:
                continue
            if address in seen_addresses:
                continue

            seen_addresses.add(address)
            solana_tokens.append({
                "chain": "solana",
                "address": address,
                "url": token.get("url"),
                "description": token.get("description"),
                "icon": token.get("icon"),
                "links": token.get("links", [])
            })

        ActivityLogger.info(
            f"Discovered {len(solana_tokens)} Solana token profiles."
        )
        return solana_tokens
