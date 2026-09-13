"""
Nakama Token Refresher - Multi Account

Refreshes Nakama session tokens and keeps the newest refresh token in:
  - data/tokens.json
  - database.json

IMPORTANT:
- Nakama decides whether a refresh token is valid.
- This script does NOT locally reject refresh tokens based on JWT expiration.
- It tries the current stored token first, then every Railway
  TOKEN_N / REFRESH_TOKEN_N account.
- Newly returned tokens are saved immediately.
- The refresher stays running if all current refresh attempts fail.
"""

import argparse
import base64
import json
import os
import ssl
import time
import traceback
from pathlib import Path
from urllib import request, error

from storage import (
    get_public_token_raw,
    set_public_token_raw,
    decode_jwt_exp,
    seconds_until_expiry,
)


# ============================================================================
# CONFIG
# ============================================================================

HOST = os.getenv(
    "NAKAMA_HOST",
    "https://animalcompany.us-east1.nakamacloud.io"
)

# Your existing fallback server key is preserved.
SERVER_KEY = os.getenv(
    "NAKAMA_SERVER_KEY",
    "6URuTSlDKKfYbuDW"
)

REFRESH_URL = f"{HOST.rstrip('/')}/v2/account/session/refresh"

# Maximum time between checks.
REFRESH_INTERVAL = int(
    os.getenv(
        "REFRESH_INTERVAL_SECONDS",
        "120"
    )
)

if not SERVER_KEY:
    print(
        "[REFRESH] ❌ NAKAMA_SERVER_KEY is missing."
    )


# ============================================================================
# PATHS / SHARED STORAGE
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent

SHARED_DB = BASE_DIR / "database.json"


def load_shared_refresh_token():
    """
    Read the newest refresh token from database.json.
    """

    try:
        if SHARED_DB.exists():

            data = json.loads(
                SHARED_DB.read_text(
                    encoding="utf-8"
                )
            )

            tokens = data.get(
                "tokens",
                []
            )

            if (
                tokens
                and isinstance(
                    tokens[0],
                    dict
                )
            ):

                return str(
                    tokens[0].get(
                        "refresh_token",
                        ""
                    )
                ).strip()

    except Exception as exc:

        print(
            f"[REFRESH] ⚠️ Could not read database.json: {exc}"
        )

    return ""


def save_shared_refresh_token(
    refresh_token
):
    """
    Save the newest refresh token to database.json.
    """

    if not refresh_token:
        return

    try:

        data = {}

        if SHARED_DB.exists():

            try:

                data = json.loads(
                    SHARED_DB.read_text(
                        encoding="utf-8"
                    )
                )

            except Exception:

                data = {}

        if not isinstance(
            data.get("tokens"),
            list
        ):

            data["tokens"] = []

        if (
            data["tokens"]
            and isinstance(
                data["tokens"][0],
                dict
            )
        ):

            data["tokens"][0][
                "refresh_token"
            ] = refresh_token

        else:

            data["tokens"].insert(
                0,
                {
                    "refresh_token":
                    refresh_token
                }
            )

        SHARED_DB.write_text(
            json.dumps(
                data,
                indent=2
            ),
            encoding="utf-8"
        )

        print(
            "[REFRESH] 💾 Saved newest refresh token "
            "to database.json"
        )

    except Exception as exc:

        print(
            "[REFRESH] ❌ Failed to save shared "
            f"refresh token: {exc}"
        )


# ============================================================================
# LOAD RAILWAY ACCOUNTS
# ============================================================================

def load_accounts():
    """
    Load:

        TOKEN_1 / REFRESH_TOKEN_1
        TOKEN_2 / REFRESH_TOKEN_2
        TOKEN_3 / REFRESH_TOKEN_3
        ...

    No expiration check is performed here.

    Nakama itself decides whether the refresh token is valid.
    """

    accounts = []

    i = 1

    while True:

        token = os.getenv(
            f"TOKEN_{i}",
            ""
        ).strip()

        refresh = os.getenv(
            f"REFRESH_TOKEN_{i}",
            ""
        ).strip()

        # Stop when the next account pair is missing.
        if not token or not refresh:
            break

        accounts.append(
            {
                "token": token,

                "refresh_token": refresh,

                "label": f"account_{i}",
            }
        )

        i += 1

    # ------------------------------------------------------------------------
    # Legacy fallback
    # ------------------------------------------------------------------------

    if not accounts:

        token = os.getenv(
            "INITIAL_TOKEN",
            ""
        ).strip()

        refresh = os.getenv(
            "INITIAL_REFRESH_TOKEN",
            ""
        ).strip()

        if token and refresh:

            accounts.append(
                {
                    "token": token,

                    "refresh_token": refresh,

                    "label": "account_1 (legacy)",
                }
            )

    return accounts


# ============================================================================
# INITIAL TOKEN LOADING
# ============================================================================

def load_tokens(accounts):
    """
    Load the currently stored token pair.

    Priority:

        1. data/tokens.json
        2. database.json
        3. Railway account variables

    IMPORTANT:

    If the stored refresh token later receives a 401,
    refresh_with_fallback() will try every Railway account.
    """

    data = get_public_token_raw()

    stored_refresh = str(
        data.get(
            "refresh_token",
            ""
        )
    ).strip()

    stored_token = str(
        data.get(
            "token",
            ""
        )
    ).strip()

    # ------------------------------------------------------------------------
    # 1. data/tokens.json
    # ------------------------------------------------------------------------

    if stored_refresh:

        print(
            "[REFRESH] ✅ Found refresh token "
            "in data/tokens.json"
        )

        if stored_token:

            print(
                "[REFRESH] 📦 Existing access token "
                "also found in storage."
            )

        else:

            print(
                "[REFRESH] 📦 No existing access token."
            )

        return {
            "token": stored_token,

            "refresh_token": stored_refresh,

            # IMPORTANT:
            # Don't pretend this belongs to account_1.
            "label": "stored",
        }

    # ------------------------------------------------------------------------
    # 2. database.json
    # ------------------------------------------------------------------------

    shared_refresh = load_shared_refresh_token()

    if shared_refresh:

        print(
            "[REFRESH] ✅ Found refresh token "
            "in database.json"
        )

        tokens = {
            "token": stored_token,

            "refresh_token": shared_refresh,

            "label": "stored",
        }

        set_public_token_raw(
            tokens
        )

        return tokens

    # ------------------------------------------------------------------------
    # 3. Railway accounts
    # ------------------------------------------------------------------------

    if accounts:

        acc = accounts[0]

        print(
            "[REFRESH] ⚡ Loading from Railway "
            f"variables — using {acc['label']}"
        )

        tokens = {
            "token": acc["token"],

            "refresh_token":
            acc["refresh_token"],

            "label": acc["label"],
        }

        set_public_token_raw(
            tokens
        )

        return tokens

    # ------------------------------------------------------------------------
    # Nothing available
    # ------------------------------------------------------------------------

    raise ValueError(
        "❌ No refresh token found. "
        "Configure REFRESH_TOKEN_1 or provide "
        "a stored refresh token."
    )


# ============================================================================
# DIRECT NAKAMA REFRESH
# ============================================================================

def do_refresh(tokens):
    """
    Refresh one token directly through Nakama.

    Logs which candidate/account is being attempted without exposing
    the actual refresh token.
    """

    if not SERVER_KEY:
        raise RuntimeError(
            "NAKAMA_SERVER_KEY is not configured."
        )

    refresh_token = str(
        tokens.get("refresh_token", "")
    ).strip()

    if not refresh_token:
        raise ValueError(
            "No refresh token is available."
        )

    label = tokens.get(
        "label",
        "unknown"
    )

    # Safe identifier for troubleshooting.
    # This NEVER prints the actual token.
    token_id = (
        f"{refresh_token[:6]}..."
        f"{refresh_token[-6:]}"
        if len(refresh_token) >= 12
        else "[short-token]"
    )

    print(
        "\n" + "=" * 60
    )

    print(
        f"[REFRESH] 🎯 Candidate: {label}"
    )

    print(
        f"[REFRESH] 🔑 Refresh token: {token_id}"
    )

    print(
        f"[REFRESH] 🌐 Nakama: {REFRESH_URL}"
    )

    print(
        "[REFRESH] 📤 Sending refresh request..."
    )

    print(
        "=" * 60
    )

    # ----------------------------------------------------------------
    # Basic authentication
    # ----------------------------------------------------------------

    basic = base64.b64encode(
        f"{SERVER_KEY}:".encode()
    ).decode()

    body = json.dumps({
        "token": refresh_token
    }).encode()

    req = request.Request(
        REFRESH_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {basic}",
        },
    )

    ssl_context = ssl.create_default_context()

    try:

        with request.urlopen(
            req,
            timeout=15,
            context=ssl_context
        ) as response:

            response_body = response.read()

            status = response.status

        print(
            f"[REFRESH] 📥 Nakama response: HTTP {status}"
        )

    except error.HTTPError as exc:

        try:
            response_body = exc.read().decode(
                "utf-8",
                errors="replace"
            )
        except Exception:
            response_body = ""

        print(
            "\n" + "!" * 60
        )

        print(
            f"[REFRESH] ❌ REJECTED"
        )

        print(
            f"[REFRESH] 🎯 Candidate: {label}"
        )

        print(
            f"[REFRESH] 🔑 Token: {token_id}"
        )

        print(
            f"[REFRESH] 🚫 HTTP {exc.code}"
        )

        print(
            f"[REFRESH] 📥 Nakama: {response_body}"
        )

        print(
            "!" * 60
        )

        # Let refresh_with_fallback() try the next candidate.
        raise

    except Exception as exc:

        print(
            "\n" + "!" * 60
        )

        print(
            f"[REFRESH] ❌ NETWORK/REQUEST ERROR"
        )

        print(
            f"[REFRESH] 🎯 Candidate: {label}"
        )

        print(
            f"[REFRESH] 🔑 Token: {token_id}"
        )

        print(
            f"[REFRESH] Error: {exc}"
        )

        print(
            "!" * 60
        )

        raise

    # ----------------------------------------------------------------
    # Parse response
    # ----------------------------------------------------------------

    try:

        data = json.loads(
            response_body
        )

    except Exception as exc:

        print(
            f"[REFRESH] ❌ Invalid JSON from Nakama: {exc}"
        )

        raise

    new_access_token = str(
        data.get(
            "token",
            ""
        )
    ).strip()

    new_refresh_token = str(
        data.get(
            "refresh_token",
            ""
        )
    ).strip()

    if not new_access_token:

        print(
            f"[REFRESH] ❌ {label} was accepted, "
            "but Nakama returned no access token."
        )

        raise RuntimeError(
            "Nakama returned no access/session token."
        )

    # Nakama may rotate the refresh token.
    if not new_refresh_token:
        new_refresh_token = refresh_token

        print(
            "[REFRESH] ⚠️ Nakama did not return a "
            "new refresh token; keeping current one."
        )
    else:

        new_token_id = (
            f"{new_refresh_token[:6]}..."
            f"{new_refresh_token[-6:]}"
            if len(new_refresh_token) >= 12
            else "[short-token]"
        )

        if new_refresh_token != refresh_token:

            print(
                "[REFRESH] 🔄 Nakama ROTATED the refresh token."
            )

            print(
                f"[REFRESH] 🔑 New refresh token: {new_token_id}"
            )

        else:

            print(
                "[REFRESH] 🔒 Refresh token was unchanged."
            )

    # ----------------------------------------------------------------
    # Update current pair
    # ----------------------------------------------------------------

    tokens["token"] = new_access_token

    tokens["refresh_token"] = new_refresh_token

    # ----------------------------------------------------------------
    # Save newest pair
    # ----------------------------------------------------------------

    set_public_token_raw({
        "token": tokens["token"],
        "refresh_token": tokens["refresh_token"],
    })

    save_shared_refresh_token(
        tokens["refresh_token"]
    )

    print(
        "\n" + "=" * 60
    )

    print(
        f"[REFRESH] ✅ ACCEPTED: {label}"
    )

    print(
        f"[REFRESH] 💾 Saved newest token pair."
    )

    print(
        "=" * 60
    )

    # ----------------------------------------------------------------
    # Access-token expiration
    # ----------------------------------------------------------------

    try:

        ttl = seconds_until_expiry(
            tokens["token"]
        )

        exp = decode_jwt_exp(
            tokens["token"]
        )

        if exp:

            exp_time = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(exp)
            )

            print(
                f"[REFRESH] ⏰ Access token expires: "
                f"{exp_time}"
            )

            print(
                f"[REFRESH] ⏳ Access token TTL: {ttl}s"
            )

    except Exception:

        pass

    return tokens
# ============================================================================
# BUILD FALLBACK CANDIDATES
# ============================================================================

def build_candidates(
    current,
    accounts
):
    """
    Build a unique list of candidates.

    Order:

        1. Current stored/current token
        2. account_1
        3. account_2
        4. account_3
        ...

    No JWT expiration checks are performed.
    """

    candidates = []

    seen = set()

    def add(candidate):

        if not candidate:
            return

        refresh = str(
            candidate.get(
                "refresh_token",
                ""
            )
        ).strip()

        if not refresh:
            return

        # Don't try the exact same refresh token twice.
        if refresh in seen:
            return

        seen.add(
            refresh
        )

        candidates.append(
            {
                "token": str(
                    candidate.get(
                        "token",
                        ""
                    )
                ).strip(),

                "refresh_token":
                refresh,

                "label":
                candidate.get(
                    "label",
                    "unknown"
                ),
            }
        )

    # Current stored token first.
    add(current)

    # Then every Railway account.
    for account in accounts:

        add(account)

    return candidates


# ============================================================================
# REFRESH WITH ACCOUNT FALLBACK
# ============================================================================

def refresh_with_fallback(tokens, accounts):
    candidates = []

    # Current token first
    if tokens and tokens.get("refresh_token"):
        candidates.append({
            "label": tokens.get("label", "current_storage"),
            "refresh_token": tokens["refresh_token"]
        })

    # Then all configured accounts
    for account in accounts:
        refresh_token = account.get("refresh_token")

        if refresh_token:
            candidates.append({
                "label": account.get("label", "unknown_account"),
                "refresh_token": refresh_token
            })

    # Remove duplicate refresh tokens
    seen = set()
    unique_candidates = []

    for candidate in candidates:
        token = candidate["refresh_token"]

        if token not in seen:
            seen.add(token)
            unique_candidates.append(candidate)

    print(
        f"[REFRESH] 🔎 Testing {len(unique_candidates)} refresh-token candidate(s)..."
    )

    for candidate in unique_candidates:
        label = candidate["label"]
        refresh_token = candidate["refresh_token"]

        # Safe fingerprint — NEVER prints the full token
        if len(refresh_token) >= 12:
            fingerprint = (
                f"{refresh_token[:6]}..."
                f"{refresh_token[-6:]}"
            )
        else:
            fingerprint = "(token too short to fingerprint)"

        print("")
        print("[REFRESH] ----------------------------------------")
        print(f"[REFRESH] 👤 Account: {label}")
        print(f"[REFRESH] 🔑 Token candidate: {fingerprint}")
        print("[REFRESH] 🔄 Sending refresh request to Nakama...")

        try:
            result = do_refresh({
                "refresh_token": refresh_token,
                "label": label
            })

            if result:
                print(
                    f"[REFRESH] ✅ Nakama ACCEPTED account: {label}"
                )
                print(
                    f"[REFRESH] ✅ Successful token candidate: {fingerprint}"
                )

                result["label"] = label
                return result

        except Exception as exc:
            error_text = str(exc)

            print(
                f"[REFRESH] ❌ Nakama REJECTED account: {label}"
            )
            print(
                f"[REFRESH] ❌ Rejected token candidate: {fingerprint}"
            )
            print(
                f"[REFRESH] ❌ Reason: {error_text}"
            )

            continue

    print("")
    print("[REFRESH] ❌ Nakama rejected ALL refresh-token candidates.")
    return None

# ============================================================================
# MAIN
# ============================================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--loop",
        action="store_true"
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------------
    # Startup information
    # ------------------------------------------------------------------------

    print(
        "[REFRESH] Process started",
        flush=True
    )

    print(
        "[REFRESH] TOKEN_1 present:",
        bool(
            os.getenv(
                "TOKEN_1"
            )
        ),
        flush=True
    )

    print(
        "[REFRESH] REFRESH_TOKEN_1 present:",
        bool(
            os.getenv(
                "REFRESH_TOKEN_1"
            )
        ),
        flush=True
    )

    # ------------------------------------------------------------------------
    # Load Railway accounts
    # ------------------------------------------------------------------------

    accounts = load_accounts()

    print(
        "\n" + "=" * 60
    )

    print(
        "🔄 PUBLIC TOKEN REFRESHER (Multi-Account)"
    )

    print(
        f"   Host:     {HOST}"
    )

    print(
        f"   Interval: {REFRESH_INTERVAL}s"
    )

    print(
        f"   Accounts: {len(accounts)} loaded "
        f"({', '.join(a['label'] for a in accounts) or 'none'})"
    )

    print(
        "=" * 60
    )

    # ------------------------------------------------------------------------
    # Load current token
    # ------------------------------------------------------------------------

    try:

        tokens = load_tokens(
            accounts
        )

    except Exception as exc:

        print(
            f"[REFRESH] ❌ Startup failed: {exc}"
        )

        return

    # ------------------------------------------------------------------------
    # One-time mode
    # ------------------------------------------------------------------------

    if not args.loop:

        try:

            refresh_with_fallback(
                tokens,
                accounts
            )

        except Exception as exc:

            print(
                f"[REFRESH] ❌ Single refresh failed: {exc}"
            )

            traceback.print_exc()

        return

    # ------------------------------------------------------------------------
    # Loop mode
    # ------------------------------------------------------------------------

    print(
        f"[REFRESH] 🔁 Loop active — "
        f"checking every {REFRESH_INTERVAL}s\n"
    )

    while True:

        try:

            access_token = str(
                tokens.get(
                    "token",
                    ""
                )
            ).strip()

            # ----------------------------------------------------------------
            # No access token
            # ----------------------------------------------------------------

            if not access_token:

                print(
                    "[REFRESH] ⚠️ No access token — "
                    "refreshing now..."
                )

                tokens = refresh_with_fallback(
                    tokens,
                    accounts
                )

                continue

            # ----------------------------------------------------------------
            # Determine access-token TTL
            # ----------------------------------------------------------------

            try:

                ttl = seconds_until_expiry(
                    access_token
                )

            except Exception:

                ttl = 0

            # ----------------------------------------------------------------
            # Refresh 5 minutes before expiration
            # ----------------------------------------------------------------

            if ttl <= 300:

                print(
                    f"[REFRESH] ⚠️ Token expires "
                    f"in {ttl}s — refreshing now..."
                )

                try:

                    tokens = refresh_with_fallback(
                        tokens,
                        accounts
                    )

                except Exception as exc:

                    print(
                        "[REFRESH] ❌ All current "
                        f"refresh attempts failed: {exc}"
                    )

                    print(
                        "[REFRESH] ⏳ Retrying "
                        "in 30 seconds..."
                    )

                    # IMPORTANT:
                    # Don't permanently stop the process.
                    time.sleep(30)

            # ----------------------------------------------------------------
            # Access token is still valid
            # ----------------------------------------------------------------

            else:

                sleep_for = min(
                    REFRESH_INTERVAL,
                    max(
                        15,
                        ttl - 300
                    )
                )

                print(
                    f"[REFRESH] ⏱️ Token valid "
                    f"for {ttl}s — checking again "
                    f"in {sleep_for}s..."
                )

                time.sleep(
                    sleep_for
                )

        # --------------------------------------------------------------------
        # Ctrl+C
        # --------------------------------------------------------------------

        except KeyboardInterrupt:

            print(
                "\n[REFRESH] ⛔ Stopped by user"
            )

            break

        # --------------------------------------------------------------------
        # Unexpected error
        # --------------------------------------------------------------------

        except Exception as exc:

            print(
                f"[REFRESH] ❌ Unexpected loop error: {exc}"
            )

            traceback.print_exc()

            time.sleep(30)


# ============================================================================
# START
# ============================================================================

if __name__ == "__main__":

    main()