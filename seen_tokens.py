import json
import os
import logging
import time
from threading import Lock

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

SEEN_FILE = os.path.join(DATA_DIR, "seen_tokens.json")

# Keep tokens only if under this age (8 hrs)
MAX_AGE_SECONDS = 8 * 60 * 60

# Module-level lock to avoid concurrent writes from threads
_FILE_LOCK = Lock()


def _now_ts() -> int:
    return int(time.time())


def make_seen_key(chainId: str, tokenAddress: str | None = None, dexId: str | None = None, pairAddress: str | None = None):
    """
    Build a stable key:
      - Prefer pairAddress if provided (most unique/stable)
      - Else fall back to (chainId, CA) only (ignore dexId to prevent duplicates).
    """
    if pairAddress:
        return (chainId, "PAIR", pairAddress)
    return (chainId, "CA", tokenAddress)


def load_seen_tokens():
    """
    Load seen tokens from file and prune anything older than MAX_AGE_SECONDS.
    """
    seen_set = set()
    seen_dict = {}

    if not os.path.exists(SEEN_FILE):
        return seen_set, seen_dict

    try:
        with open(SEEN_FILE, "r") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Error loading seen tokens: {e}")
        return seen_set, seen_dict

    now = _now_ts()

    for chainId, entries in (data or {}).items():
        kept = []
        if not isinstance(entries, list):
            continue

        for entry in entries:
            ca = entry.get("CA")
            dexId = entry.get("dexId")
            tokenName = entry.get("tokenName")
            pairAddress = entry.get("pairAddress")
            firstSeenTs = entry.get("firstSeenTs")

            if not isinstance(firstSeenTs, int):
                continue

            # Prune old
            if now - firstSeenTs > MAX_AGE_SECONDS:
                continue

            key = make_seen_key(chainId, tokenAddress=ca, pairAddress=pairAddress)
            seen_set.add(key)

            kept.append({
                "CA": ca,
                "dexId": dexId,
                "tokenName": tokenName,
                "pairAddress": pairAddress,   # ✅ fixed (no longer overwrites with CA)
                "firstSeenTs": firstSeenTs,
                "ageAtFirstSeen": entry.get("ageAtFirstSeen"),
            })

        if kept:
            seen_dict[chainId] = kept

    return seen_set, seen_dict


def save_seen_tokens(seen_dict: dict):
    with _FILE_LOCK:
        try:
            with open(SEEN_FILE, "w") as f:
                json.dump(seen_dict, f, indent=2)
            logging.info(f"Saved {len(seen_dict)} chains into {SEEN_FILE}")
        except Exception as e:
            logging.error(f"Could not save seen tokens: {e}")


def add_seen_token(
    seen_set: set,
    seen_dict: dict,
    chainId: str,
    tokenAddress: str,
    dexId: str,
    tokenName: str,
    age_minutes: int,
    age_seconds: int,
    pairAddress: str | None = None,
):
    """
    Add a new token entry (under its chainId) and prune >8h entries.
    """
    key = make_seen_key(chainId, tokenAddress=tokenAddress, pairAddress=pairAddress)
    if key in seen_set:
        logging.debug(f"Skipping duplicate token {tokenAddress} on {chainId}")
        return  # already seen

    seen_set.add(key)

    if chainId not in seen_dict:
        seen_dict[chainId] = []

    now = _now_ts()
    seen_dict[chainId].append({
        "CA": tokenAddress,
        "dexId": dexId,
        "tokenName": tokenName,
        "pairAddress": pairAddress,
        "firstSeenTs": now,
        "ageAtFirstSeen": f"{age_minutes} min ({age_seconds} sec)",
    })

    # prune old
    cutoff = now - MAX_AGE_SECONDS
    seen_dict[chainId] = [
        entry for entry in seen_dict[chainId]
        if isinstance(entry.get("firstSeenTs"), int) and entry["firstSeenTs"] >= cutoff
    ]

    save_seen_tokens(seen_dict)
