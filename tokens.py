import requests
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import load_config
from seen_tokens import load_seen_tokens, add_seen_token, make_seen_key
from notifiers import send_to_slack, send_to_discord

TOKEN_PROFILES_API = "https://api.dexscreener.com/token-profiles/latest/v1"
PAIR_API_TEMPLATE = "https://api.dexscreener.com/token-pairs/v1/{chainId}/{tokenAddress}"

# Thresholds (could be moved to config.json)
MIN_LIQUIDITY = 20000
MIN_FDV = 20000
MIN_MARKET_CAP = 20000

# === Rate limiter ===
class RateLimiter:
    def __init__(self, rate_per_sec):
        self.min_interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.last_call = 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            wait_time = self.min_interval - (now - self.last_call)
            if wait_time > 0:
                time.sleep(wait_time)
            self.last_call = time.time()

# Limiters
profiles_limiter = RateLimiter(1)   # 1 req/sec (60/min)
pairs_limiter = RateLimiter(5)      # 5 req/sec (300/min)


def fetch_latest_tokens():
    try:
        profiles_limiter.wait()
        resp = requests.get(TOKEN_PROFILES_API, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list):
            tokens = data
        elif isinstance(data, dict) and "tokens" in data:
            tokens = data["tokens"]
        else:
            logging.warning("Unexpected API response structure")
            return []

        sol_tokens = [
            {"chainId": t.get("chainId"), "tokenAddress": t.get("tokenAddress")}
            for t in tokens if t.get("chainId") == "solana" and t.get("tokenAddress")
        ]
        return sol_tokens
    except Exception as e:
        logging.error(f"Error fetching latest tokens: {e}")
        return []


def check_usdc_pair(chainId, tokenAddress, seen_set, seen_dict, config):
    try:
        url = PAIR_API_TEMPLATE.format(chainId=chainId, tokenAddress=tokenAddress)
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        pairs = resp.json()

        if not isinstance(pairs, list):
            return False

        now_ms = int(time.time() * 1000)
        one_hour_ms = 365 * 24 * 60 * 60 * 1000 #make it a year

        for pair in pairs:
            tokenName = pair.get("baseToken", {}).get("name", "Unknown")
            dexId = pair.get("dexId", "unknown")
            pairAddress = pair.get("pairAddress")

            # === Stable duplicate check (prefer pairAddress) ===
            key = make_seen_key(chainId, tokenAddress=tokenAddress, dexId=dexId, pairAddress=pairAddress)
            if key in seen_set:
                continue

            # Basic filters
            liquidity_val = pair.get("liquidity", {}).get("usd")
            if not isinstance(liquidity_val, (int, float)) or liquidity_val < MIN_LIQUIDITY:
                continue

            fdv = pair.get("fdv")
            market_cap = pair.get("marketCap")
            if not isinstance(fdv, (int, float)) or fdv < MIN_FDV:
                continue
            if not isinstance(market_cap, (int, float)) or market_cap < MIN_MARKET_CAP:
                continue

            # Quote must be one of your USDC addresses
            quote = pair.get("quoteToken", {})
            if quote.get("address") not in config.get("USDC_ADDRESSES", []):
                continue

            # Age from pairCreatedAt
            created_at = pair.get("pairCreatedAt")
            if not created_at:
                continue

            age_ms = now_ms - created_at
            if age_ms > one_hour_ms:
                continue  # keep results very fresh; adjust if desired

            # ✅ Correct age calculation
            age_seconds_total = int(age_ms / 1000)
            age_minutes = age_seconds_total // 60
            age_seconds = age_seconds_total % 60

            dex_url = pair.get("url", f"https://dexscreener.com/{chainId}/{tokenAddress}")
            priceUsd = pair.get("priceUsd", "N/A")

            imageUrl = (
                pair.get("info", {}).get("imageUrl")
                or pair.get("baseToken", {}).get("icon")
                or None
            )

            logging.info(
                f"New Token Alert -> {tokenName} ({tokenAddress}) | "
                f"DEX: {dexId} | Price: {priceUsd} | FDV: {fdv} | "
                f"MarketCap: {market_cap} | Liquidity: {liquidity_val} | "
                f"Age: {age_minutes} min {age_seconds} sec"
            )

            # Notify (age displayed in your updated notifiers)
            send_to_slack(
                tokenAddress, tokenName, dexId, dex_url,
                fdv, market_cap, priceUsd, liquidity_val,
                imageUrl, age_minutes, age_seconds
            )
            send_to_discord(
                tokenAddress, tokenName, dexId, dex_url,
                fdv, market_cap, priceUsd, liquidity_val,
                imageUrl, age_minutes, age_seconds
            )

            # Mark as seen (stores pairAddress + timestamp; prunes >8h)
            add_seen_token(
                seen_set, seen_dict,
                chainId, tokenAddress, dexId, tokenName,
                age_minutes, age_seconds,
                pairAddress=pairAddress
            )

            # Stop after first matching pair for this tokenAddress
            return True

        return False

    except Exception as e:
        logging.error(f"{tokenAddress} : error fetching pairs: {e}")
        return False

def process_tokens():
    config = load_config()
    seen_set, seen_dict = load_seen_tokens()
    logging.info(f"Loaded {len(seen_set)} previously alerted pair entries (<=8h).")

    tokens = fetch_latest_tokens()
    logging.info(f"Fetched {len(tokens)} Solana tokens. Checking pairs...")

    with ThreadPoolExecutor(max_workers=5) as executor:   # ⚖ keep modest concurrency
        futures = [
            executor.submit(check_usdc_pair, t["chainId"], t["tokenAddress"], seen_set, seen_dict, config)
            for t in tokens
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Thread error: {e}")
