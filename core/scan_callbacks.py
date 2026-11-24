from core.config import RpcConfig
from core.momentum_bot import MomentumBot
from core.new_gem_hunter import NewGemHunter
from core.provider_errors import ProviderError
from core.safety_bot import SafetyBot
from core.volume_scanner import VolumeScanner


def create_scan_functions(rpc_config=None):
    rpc_config = (
        RpcConfig.load()
        if rpc_config is None
        else rpc_config
    )

    gem_hunter = NewGemHunter()
    momentum_bot = MomentumBot(gem_hunter=gem_hunter)
    volume_scanner = VolumeScanner(gem_hunter=gem_hunter)
    safety_bot = SafetyBot()
    safety_bot.RPC_URL = rpc_config.primary_url
    safety_bot.RPC_FALLBACK_URL = rpc_config.fallback_url
    safety_token_index = 0

    def scan_safety():
        nonlocal safety_token_index
        tokens = gem_hunter.scan_latest_tokens()
        if not tokens:
            return []

        token = tokens[safety_token_index % len(tokens)]
        safety_token_index = (safety_token_index + 1) % len(tokens)
        result = safety_bot.check_token(
            token["address"],
            market_data=token["market_data"],
        )
        if result.get("checks", {}).get("on_chain_verification") == "FAILED":
            raise ProviderError(
                f"Safety verification failed for {token['address']}"
            )
        return [result]

    return {
        "NEW GEM HUNTER": gem_hunter.scan_latest_tokens,
        "MOMENTUM BOT": momentum_bot.analyze_latest_tokens,
        "VOLUME SCANNER": volume_scanner.analyze_latest_tokens,
        "SAFETY BOT": scan_safety,
    }
