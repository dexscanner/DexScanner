import requests
import logging
import json
from config import load_config

config = load_config()

SLACK_WEBHOOK_URL = config.get("SLACK_WEBHOOK_URL")
DISCORD_WEBHOOK_URLS = config.get("DISCORD_WEBHOOK_URLS", [])

def send_to_slack(
    tokenAddress,
    tokenName,
    dexId,
    dex_url,
    fdv,
    market_cap,
    priceUsd,
    liquidity,
    imageUrl=None,
    age_minutes=None,
    age_seconds=None,
):
    # Slack integration is disabled.
    return

    # --- old Slack code kept for reference ---
    # fallback_text = f"🚨 New {tokenName} {dexId.upper()} Pair: {tokenName} [{tokenAddress}]"
    # if age_minutes is not None and age_seconds is not None:
    #     if age_minutes > 0:
    #         age_text = f"⏱️ *Age:* {age_minutes} min {age_seconds} sec\n"
    #     else:
    #         age_text = f"⏱️ *Age:* {age_seconds} sec\n"
    # else:
    #     age_text = ""
    # ... payload and requests.post remains the same


def send_to_discord(
    tokenAddress,
    tokenName,
    dexId,
    dex_url,
    fdv,
    market_cap,
    priceUsd,
    liquidity,
    imageUrl=None,
    age_minutes=None,
    age_seconds=None,
):
    if not DISCORD_WEBHOOK_URLS:
        return

    # Smart age formatting
    if age_minutes is not None and age_seconds is not None:
        if age_minutes > 0:
            age_text = f"⏱️ **Age:** {age_minutes} min {age_seconds} sec\n"
        else:
            age_text = f"⏱️ **Age:** {age_seconds} sec\n"
    else:
        age_text = ""

    payload = {
        "embeds": [
            {
                "title": f"🚨 {tokenName}",
                "url": dex_url,
                "description": (
                    f"💠 **CA:** `{tokenAddress}`\n"
                    f"🪙 **DEX:** {dexId.upper()}\n"
                    f"💵 **Price:** ${priceUsd}\n"
                    f"📊 **Liquidity:** ${liquidity}\n"
                    f"🏦 **Market Cap:** ${market_cap}\n"
                    f"📈 **FDV:** ${fdv}\n"
                    f"{age_text}"
                ),
                "thumbnail": {"url": imageUrl} if imageUrl else None,
                "color": 5814783,
            }
        ]
    }

    for url in DISCORD_WEBHOOK_URLS:
        try:
            resp = requests.post(
                url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code not in (200, 204):
                logging.error(f"Discord error [{url}]: {resp.status_code} {resp.text}")
        except Exception as e:
            logging.error(f"Error sending to Discord [{url}]: {e}")
