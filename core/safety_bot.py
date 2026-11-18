
import math
import os
import requests
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from core.activity_logger import ActivityLogger
from core.provider_errors import ProviderError


class SafetyBot:

    RPC_URL = os.environ.get(
        "NEXUS_SOLANA_RPC_URL",
        "https://api.mainnet-beta.solana.com",
    )
    RPC_FALLBACK_URL = os.environ.get("NEXUS_SOLANA_RPC_FALLBACK_URL")

    TOKEN_PROGRAMS = {
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
    }

    MIN_LIQUIDITY_USD = 10000
    MIN_RPC_REQUEST_INTERVAL_SECONDS = 0.5

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "NEXUS-AI/1.0"
        })
        self._rpc_lock = threading.Lock()
        self._last_rpc_request_at = 0.0
        self._rpc_cooldown_until = 0.0

    @staticmethod
    def _finite_nonnegative(value, field_name):
        if isinstance(value, bool):
            raise ValueError(f"Invalid {field_name}")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"Invalid {field_name}") from error
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"Invalid {field_name}")
        return number

    @staticmethod
    def _retry_delay(response, attempt):
        headers = getattr(response, "headers", {})
        retry_after = headers.get("Retry-After")
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = (
                        retry_at - datetime.now(timezone.utc)
                    ).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    delay = 2 ** (attempt + 1)
        else:
            delay = 2 ** (attempt + 1)

        return min(max(delay, 1.0), 30.0)

    def _rpc_request(self, method, params):
        now = time.monotonic()
        if now < self._rpc_cooldown_until:
            retry_in = self._rpc_cooldown_until - now
            raise ProviderError(
                f"Solana RPC rate-limit cooldown active; "
                f"retry in {retry_in:.1f} seconds"
            )

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }

        endpoints = [self.RPC_URL]
        if self.RPC_FALLBACK_URL and self.RPC_FALLBACK_URL != self.RPC_URL:
            endpoints.append(self.RPC_FALLBACK_URL)

        last_error = None
        for endpoint in endpoints:
            for attempt in range(3):
                try:
                    with self._rpc_lock:
                        delay = (
                            self.MIN_RPC_REQUEST_INTERVAL_SECONDS
                            - (time.monotonic() - self._last_rpc_request_at)
                        )
                        if delay > 0:
                            time.sleep(delay)
                        self._last_rpc_request_at = time.monotonic()

                    response = self.session.post(
                        endpoint,
                        json=payload,
                        timeout=20
                    )

                    if response.status_code == 429 and attempt < 2:
                        wait_time = self._retry_delay(response, attempt)
                        ActivityLogger.warning(
                            "Solana RPC returned HTTP 429; "
                            f"retrying in {wait_time:g} seconds."
                        )
                        time.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    data = response.json()

                    if not isinstance(data, dict):
                        raise ValueError("Invalid RPC response structure")
                    if data.get("error"):
                        raise ValueError(str(data["error"]))

                    self._rpc_cooldown_until = 0.0
                    return data.get("result")

                except requests.RequestException as error:
                    last_error = error
                    status_code = getattr(
                        getattr(error, "response", None),
                        "status_code",
                        None,
                    )
                    if (
                        status_code is not None
                        and 400 <= status_code < 500
                        and status_code != 429
                    ):
                        break
                    if status_code == 429:
                        self._rpc_cooldown_until = max(
                            self._rpc_cooldown_until,
                            time.monotonic()
                            + self._retry_delay(
                                getattr(error, "response", None),
                                attempt,
                            ),
                        )
                    if attempt < 2:
                        time.sleep(2 ** (attempt + 1))

            if endpoint != endpoints[-1]:
                ActivityLogger.warning(
                    "Solana RPC endpoint failed; trying the next configured endpoint."
                )

        status_code = getattr(
            getattr(last_error, "response", None),
            "status_code",
            None,
        )
        if status_code == 429:
            error_detail = "HTTP 429 rate limit"
        elif status_code is not None:
            error_detail = f"HTTP {status_code}"
        elif last_error is not None:
            error_detail = type(last_error).__name__
        else:
            error_detail = "invalid response"
        raise ProviderError(
            f"Solana RPC request failed: {error_detail}"
        ) from last_error

    def check_token(self, token_address, market_data=None):

        risks = []
        warnings = []
        checks = {}

        checks["address_present"] = bool(token_address)

        if not token_address:
            return {
                "token_address": None,
                "status": "BLOCKED",
                "checks": checks,
                "risks": ["Missing token address"],
                "warnings": warnings
            }

        try:
            account = self._rpc_request(
                "getAccountInfo",
                [
                    token_address,
                    {"encoding": "jsonParsed"}
                ]
            )

            value = account.get("value") if account else None

            if not value:
                raise ValueError("Token mint account not found")

            program_owner = value.get("owner")

            if program_owner not in self.TOKEN_PROGRAMS:
                risks.append("Unknown token program")
                checks["token_program"] = False
            else:
                checks["token_program"] = True

            parsed = (
                value.get("data", {})
                .get("parsed", {})
            )

            if parsed.get("type") != "mint":
                raise ValueError("Account is not a parsed token mint")

            info = parsed.get("info", {})

            mint_authority = info.get("mintAuthority")
            freeze_authority = info.get("freezeAuthority")

            checks["mint_authority"] = mint_authority is None
            checks["freeze_authority"] = freeze_authority is None

            if mint_authority is not None:
                risks.append("Mint authority is still enabled")

            if freeze_authority is not None:
                risks.append("Freeze authority is still enabled")

            if program_owner == (
                "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
            ):
                warnings.append(
                    "Token-2022 detected: extensions need additional review"
                )

            supply_result = self._rpc_request(
                "getTokenSupply",
                [token_address]
            )

            if not isinstance(supply_result, dict):
                raise ValueError("Invalid token supply response")
            supply_info = supply_result.get("value")
            if not isinstance(supply_info, dict):
                raise ValueError("Token supply data is unavailable")
            total_supply = self._finite_nonnegative(
                supply_info.get("uiAmount"),
                "token supply",
            )

            if total_supply <= 0:
                risks.append("Invalid or unavailable token supply")

            largest_result = self._rpc_request(
                "getTokenLargestAccounts",
                [token_address]
            )

            if not isinstance(largest_result, dict):
                raise ValueError("Invalid largest-accounts response")
            largest_accounts = largest_result.get("value")
            if not isinstance(largest_accounts, list):
                raise ValueError("Largest-account data is unavailable")

            observed_accounts = largest_accounts[:20]
            top10_amount = 0.0
            account_amounts = []
            account_addresses = []
            for item in observed_accounts:
                if not isinstance(item, dict):
                    raise ValueError("Invalid token account data")
                account_amount = self._finite_nonnegative(
                    item.get("uiAmount"),
                    "token account balance",
                )
                account_amounts.append(account_amount)
                address = item.get("address")
                if not isinstance(address, str) or not address:
                    raise ValueError("Invalid token account address")
                account_addresses.append(address)

            top10_amount = sum(account_amounts[:10])

            concentration = None

            if total_supply > 0:
                concentration = (
                    top10_amount / total_supply
                ) * 100
            warnings.append(
                "Concentration is based on token accounts, not verified "
                "independent owners"
            )

            checks["top10_account_concentration"] = concentration

            if not account_addresses:
                raise ValueError("No token accounts were returned")

            owners_result = self._rpc_request(
                "getMultipleAccounts",
                [
                    account_addresses,
                    {"encoding": "jsonParsed"},
                ],
            )
            if not isinstance(owners_result, dict):
                raise ValueError("Invalid token-account owner response")
            owner_accounts = owners_result.get("value")
            if (
                not isinstance(owner_accounts, list)
                or len(owner_accounts) != len(observed_accounts)
            ):
                raise ValueError("Incomplete token-account owner data")

            owner_balances = {}
            for owner_account, account_amount in zip(
                owner_accounts,
                account_amounts,
            ):
                if not isinstance(owner_account, dict):
                    raise ValueError("Invalid token-account owner data")
                parsed_info = (
                    owner_account.get("data", {})
                    .get("parsed", {})
                    .get("info", {})
                )
                if not isinstance(parsed_info, dict):
                    raise ValueError("Invalid parsed token-account owner")
                owner = parsed_info.get("owner")
                if not isinstance(owner, str) or not owner:
                    raise ValueError("Token-account owner is unavailable")
                owner_balances[owner] = (
                    owner_balances.get(owner, 0.0) + account_amount
                )

            top10_observed_owner_amount = sum(
                sorted(owner_balances.values(), reverse=True)[:10]
            )
            checks["top10_owner_concentration_observed"] = (
                top10_observed_owner_amount / total_supply * 100
                if total_supply > 0 else None
            )
            checks["owner_concentration_complete"] = False
            warnings.append(
                "Owner concentration covers only owners represented in "
                "the largest-account sample"
            )

            if concentration is not None and concentration >= 80:
                warnings.append(
                    "Top 10 token accounts hold at least 80% of supply"
                )

            checks["supply_available"] = total_supply > 0

        except (
            requests.RequestException,
            ProviderError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
        ) as error:

            checks["on_chain_verification"] = "FAILED"
            risks.append(
                f"On-chain verification failed: {error}"
            )

            ActivityLogger.error(
                f"SAFETY BOT verification failed for "
                f"{token_address}: {error}"
            )

        liquidity_values = []
        if not isinstance(market_data, list):
            market_data = []
            risks.append("Market data could not be verified")

        for pair in market_data:
            if not isinstance(pair, dict):
                risks.append("Invalid market data structure")
                continue
            liquidity = pair.get("liquidity_usd")
            if liquidity is None:
                continue
            try:
                liquidity = self._finite_nonnegative(
                    liquidity,
                    "market liquidity",
                )
            except ValueError:
                risks.append("Market liquidity is invalid")
                continue
            if liquidity > 0:
                liquidity_values.append(liquidity)

        best_liquidity = (
            max(liquidity_values)
            if liquidity_values else None
        )

        checks["liquidity_usd"] = best_liquidity

        if best_liquidity is None:
            risks.append("Liquidity could not be verified")

        elif best_liquidity < self.MIN_LIQUIDITY_USD:
            risks.append("Liquidity is below minimum threshold")

        status = "BLOCKED" if risks else "REVIEW_REQUIRED"

        ActivityLogger.info(
            f"SAFETY BOT result for {token_address}: {status}"
        )

        return {
            "token_address": token_address,
            "status": status,
            "checks": checks,
            "risks": risks,
            "warnings": warnings
        }
