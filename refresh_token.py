"""
refresh_token.py — Nakama Token Refresher (Multi-Account)
==========================================================
Keeps the public token pool alive using multiple accounts as fallback.

Variables en Railway:
    TOKEN_1, REFRESH_TOKEN_1   ← cuenta principal
    TOKEN_2, REFRESH_TOKEN_2   ← backup 1
    TOKEN_3, REFRESH_TOKEN_3   ← backup 2
    ... (sin límite)

    NAKAMA_HOST               ← opcional
    NAKAMA_SERVER_KEY         ← opcional
    REFRESH_INTERVAL_SECONDS  ← opcional (default 120)

Usage:
    python refresh_token.py          → refresh once
    python refresh_token.py --loop   → loop every REFRESH_INTERVAL seconds
"""

import base64
import json
import os
import time
import argparse
from urllib import request, error
import ssl
import traceback
from pathlib import Path

from storage import (
    get_public_token_raw,
    set_public_token_raw,
    decode_jwt_exp,
    is_expired,
    seconds_until_expiry,
)

# ── Config ────────────────────────────────────────────────────────────────────
HOST        = os.getenv("NAKAMA_HOST", "https://animalcompany.us-east1.nakamacloud.io")
SERVER_KEY  = os.getenv("NAKAMA_SERVER_KEY", "6URuTSlDKKfYbuDW")
REFRESH_URL = f"{HOST}/v2/account/session/refresh"
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL_SECONDS", "120"))

if not SERVER_KEY:
    print("[REFRESH] ❌ NAKAMA_SERVER_KEY is missing from environment variables.")


# ── Shared refresh-token storage ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
SHARED_DB = BASE_DIR / "database.json"

def load_shared_refresh_token():
    try:
        if SHARED_DB.exists():
            data = json.loads(SHARED_DB.read_text(encoding="utf-8"))
            tokens = data.get("tokens", [])
            if tokens and isinstance(tokens[0], dict):
                return str(tokens[0].get("refresh_token", "")).strip()
    except Exception as e:
        print(f"[REFRESH] ⚠️ Could not read shared database.json: {e}")
    return ""

def save_shared_refresh_token(refresh_token):
    if not refresh_token:
        return
    try:
        data = {}
        if SHARED_DB.exists():
            try: data = json.loads(SHARED_DB.read_text(encoding="utf-8"))
            except Exception: data = {}
        if not isinstance(data.get("tokens"), list): data["tokens"] = []
        if data["tokens"] and isinstance(data["tokens"][0], dict):
            data["tokens"][0]["refresh_token"] = refresh_token
        else:
            data["tokens"].insert(0, {"refresh_token": refresh_token})
        SHARED_DB.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("[REFRESH] 💾 Saved newest refresh token to shared database.json")
    except Exception as e:
        print(f"[REFRESH] ❌ Failed to save shared refresh token: {e}")

# ── Load accounts from env (TOKEN_1/REFRESH_TOKEN_1, TOKEN_2/..., etc.) ──────
def load_accounts() -> list[dict]:
    """
    Reads TOKEN_1/REFRESH_TOKEN_1, TOKEN_2/REFRESH_TOKEN_2, ...
    Returns a list of {token, refresh_token, label} in order.
    Stops at the first missing pair.
    """
    accounts = []
    i = 1
    while True:
        token   = os.getenv(f"TOKEN_{i}", "").strip()
        refresh = os.getenv(f"REFRESH_TOKEN_{i}", "").strip()
        if not token or not refresh:
            break
        accounts.append({
            "token":         token,
            "refresh_token": refresh,
            "label":         f"account_{i}",
        })
        i += 1

    # Backward-compat: also accept old INITIAL_TOKEN / INITIAL_REFRESH_TOKEN
    # as a fallback if no TOKEN_N vars are set
    if not accounts:
        token   = os.getenv("INITIAL_TOKEN", "").strip()
        refresh = os.getenv("INITIAL_REFRESH_TOKEN", "").strip()
        if token and refresh:
            accounts.append({
                "token":         token,
                "refresh_token": refresh,
                "label":         "account_1 (legacy)",
            })

    return accounts


def get_active_account(accounts: list[dict]) -> dict | None:
    """Return the first account whose refresh_token is still valid."""
    for acc in accounts:
        if not is_expired(acc["refresh_token"], buffer=60):
            return acc
    return None


def load_tokens(accounts: list[dict]) -> dict:
    """
    Load the token pair.

    Priority:
    1. data/tokens.json refresh token
    2. database.json shared refresh token
    3. TOKEN_1 / REFRESH_TOKEN_1 environment variables

    A stored refresh token can be used even if the access token has
    already expired, because the whole point of this script is to
    refresh the access token.
    """

    data = get_public_token_raw()

    # ---------------------------------------------------------
    # 1. Use the refresh token from data/tokens.json
    # ---------------------------------------------------------
    stored_refresh = str(data.get("refresh_token", "")).strip()

    if stored_refresh:
        print("[REFRESH] ✅ Found refresh token in data/tokens.json")

        stored_token = str(data.get("token", "")).strip()

        if stored_token:
            print("[REFRESH] 📦 Existing access token also found in storage.")
        else:
            print("[REFRESH] 📦 No existing access token — refresh will create one.")

        return {
            "token": stored_token,
            "refresh_token": stored_refresh
        }

    # ---------------------------------------------------------
    # 2. Use refresh token from shared database.json
    # ---------------------------------------------------------
    shared_refresh = load_shared_refresh_token()

    if shared_refresh:
        print("[REFRESH] ✅ Found refresh token in shared database.json")

        stored_token = str(data.get("token", "")).strip()

        tokens = {
            "token": stored_token,
            "refresh_token": shared_refresh
        }

        set_public_token_raw(tokens)

        return tokens

    # ---------------------------------------------------------
    # 3. Fall back to Railway TOKEN_1 / REFRESH_TOKEN_1
    # ---------------------------------------------------------
    acc = get_active_account(accounts)

    if acc:
        print(f"[REFRESH] ⚡ Loading from Railway variables — using {acc['label']}")

        tokens = {
            "token": acc["token"],
            "refresh_token": acc["refresh_token"]
        }

        set_public_token_raw(tokens)

        return tokens

    # ---------------------------------------------------------
    # Nothing available
    # ---------------------------------------------------------
    raise ValueError(
        "❌ No refresh token found.\n"
        "Put a valid refresh token in data/tokens.json, "
        "database.json, or Railway REFRESH_TOKEN_1."
    )
# ── Refresh call ──────────────────────────────────────────────────────────────
def do_refresh(tokens: dict) -> dict:
    if not SERVER_KEY:
        raise RuntimeError("NAKAMA_SERVER_KEY is not configured.")
    print(f"\n[REFRESH] 🔄 Refreshing token...")

    basic = base64.b64encode(f"{SERVER_KEY}:".encode()).decode()
    body  = json.dumps({"token": tokens["refresh_token"]}).encode()

    req = request.Request(
        REFRESH_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Basic {basic}",
        },
    )

    ssl_context = ssl.create_default_context()
    with request.urlopen(req, timeout=15, context=ssl_context) as resp:
        data = json.loads(resp.read())

    tokens["token"]         = data.get("token",         tokens["token"])
    tokens["refresh_token"] = data.get("refresh_token", tokens["refresh_token"])

    set_public_token_raw(tokens)
    save_shared_refresh_token(tokens["refresh_token"])

    ttl      = seconds_until_expiry(tokens["token"])
    exp_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(decode_jwt_exp(tokens["token"])))
    print(f"[REFRESH] ✅ Token refreshed! Expires: {exp_time} (in {ttl}s)")

    return tokens


def switch_to_next_account(accounts: list[dict], current: dict) -> dict | None:
    """
    Try each account in order after the current one fails.
    Returns the first valid account, or None if all are dead.
    """
    current_label = current.get("label", "")
    # Try accounts after the current one first, then wrap around
    ordered = sorted(accounts, key=lambda a: a["label"] != current_label)
    for acc in ordered:
        if acc["label"] == current_label:
            continue
        if not is_expired(acc["refresh_token"], buffer=60):
            print(f"[REFRESH] 🔀 Switching to {acc['label']}")
            return {"token": acc["token"], "refresh_token": acc["refresh_token"], "label": acc["label"]}
    return None


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    print("[REFRESH] Process started", flush=True)
    print(
        "[REFRESH] TOKEN_1 present:",
        bool(os.getenv("TOKEN_1")),
        flush=True
    )
    print(
        "[REFRESH] REFRESH_TOKEN_1 present:",
        bool(os.getenv("REFRESH_TOKEN_1")),
        flush=True
    )

    accounts = load_accounts()

    print("\n" + "=" * 55)
    print("🔄 PUBLIC TOKEN REFRESHER (Multi-Account)")
    print(f"   Host:     {HOST}")
    print(f"   Interval: {REFRESH_INTERVAL}s")
    print(f"   Accounts: {len(accounts)} loaded ({', '.join(a['label'] for a in accounts)})")
    print("=" * 55)



    tokens = load_tokens(accounts)
    # Track which account is active for fallback purposes
    tokens.setdefault("label", accounts[0]["label"])

    if not args.loop:
        try:
            do_refresh(tokens)
        except Exception as e:
            print(f"[REFRESH] ❌ Single refresh failed: {e}")
            traceback.print_exc()
        return
    # ── Loop ──────────────────────────────────────────────────────────────────
    print(f"[REFRESH] 🔁 Loop active — every {REFRESH_INTERVAL}s\n")
    fails = 0
    MAX_FAILS = 5

    while True:
        try:
            ttl = seconds_until_expiry(tokens["token"])

            if ttl <= 300:
                print(f"[REFRESH] ⚠️ Token expires in {ttl}s — refreshing now...")
                tokens = do_refresh(tokens)
                fails = 0
            else:
                sleep_for = min(REFRESH_INTERVAL, max(15, ttl - 300))
                print(f"[REFRESH] ⏱️ Token valid for {ttl}s — checking again in {sleep_for}s...")
                time.sleep(sleep_for)

        except KeyboardInterrupt:
            print("\n[REFRESH] ⛔ Stopped by user")
            break

        except error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()
            except Exception:
                pass
            fails += 1
            print(f"[REFRESH] ❌ HTTP {e.code}: {body} (fail {fails}/{MAX_FAILS})")

            # Auth error — try next account
            if e.code in (401, 403):
                print(f"[REFRESH] 🔑 Auth error on {tokens.get('label')} — trying next account...")
                next_acc = switch_to_next_account(accounts, tokens)
                if next_acc:
                    tokens = next_acc
                    set_public_token_raw({"token": tokens["token"], "refresh_token": tokens["refresh_token"]})
                    save_shared_refresh_token(tokens["refresh_token"])
                    fails = 0
                    continue
                else:
                    print("[REFRESH] ❌ All accounts failed auth — stopping.")
                    break

            if fails >= MAX_FAILS:
                # Try next account before giving up completely
                print(f"[REFRESH] ⚠️ {MAX_FAILS} consecutive failures — trying next account...")
                next_acc = switch_to_next_account(accounts, tokens)
                if next_acc:
                    tokens = next_acc
                    set_public_token_raw({"token": tokens["token"], "refresh_token": tokens["refresh_token"]})
                    save_shared_refresh_token(tokens["refresh_token"])
                    fails = 0
                    continue
                print("[REFRESH] ❌ All accounts exhausted — stopping.")
                break

            time.sleep(30 * fails)

        except Exception as e:
            fails += 1
            print(f"[REFRESH] ❌ Error: {e} (fail {fails}/{MAX_FAILS})")
            traceback.print_exc()

            if fails >= MAX_FAILS:
                print(f"[REFRESH] ⚠️ {MAX_FAILS} consecutive failures — trying next account...")
                next_acc = switch_to_next_account(accounts, tokens)
                if next_acc:
                    tokens = next_acc
                    set_public_token_raw({"token": tokens["token"], "refresh_token": tokens["refresh_token"]})
                    save_shared_refresh_token(tokens["refresh_token"])
                    fails = 0
                    continue
                print("[REFRESH] ❌ All accounts exhausted — stopping.")
                break

            time.sleep(30 * fails)


if __name__ == "__main__":
    main()
