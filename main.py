"""
main.py — Master Launcher
===========================
Starts, in parallel threads with auto-restart:

  1. bot.py             → single Discord app, single CommandTree,
                            all slash commands (/token, /get-premium-token,
                            /donate-token, /status, etc.)
  2. refresh_token.py   → keeps the public token pool alive

IMPORTANT: only ONE discord.Client may log in with a given bot
token at a time. Running multiple Client instances concurrently
on the same token causes duplicate gateway sessions, 429 rate
limits on command sync, and intermittent "CommandNotFound"
errors. That's why every slash command lives in bot.py under one
CommandTree instead of being split across several bot processes.
"""

import os
import sys
import time
import threading
import subprocess

RESTART_DELAY = int(os.getenv("RESTART_DELAY", "10"))


def run_forever(name: str, cmd: list):
    """Run a subprocess, restart it automatically if it exits."""
    consecutive_crashes = 0
    while True:
        print(f"[MAIN] ▶️  Starting {name}...")
        try:
            result = subprocess.run(cmd, check=False)
            code   = result.returncode
        except Exception as e:
            print(f"[MAIN] ❌ {name} exception: {e}")
            code = -1

        consecutive_crashes += 1
        print(f"[MAIN] ⚠️  {name} stopped (exit {code}), crash #{consecutive_crashes}")

        delay = min(RESTART_DELAY * consecutive_crashes, 300)
        print(f"[MAIN] 🔁 Restarting {name} in {delay}s...")
        time.sleep(delay)

        if consecutive_crashes >= 10:
            print(f"[MAIN] 🔴 {name} crashed 10 times. Resetting counter — check your env vars.")
            consecutive_crashes = 0


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 EIC TOKEN BOT SYSTEM")
    print("   Bot (all commands): ✅ ON")
    print("   Token refresh:       ✅ ON")
    print("=" * 60)

    threads = [
        threading.Thread(
            target=run_forever,
            args=("Bot", ["node", "discord.js"]),
            daemon=False,
            name="Bot",
        ),
        threading.Thread(
            target=run_forever,
            args=("TokenRefresh", [sys.executable, "refresh_token.py", "--loop"]),
            daemon=False,
            name="TokenRefresh",
        ),
    ]

    for t in threads:
        t.start()

    print(f"[MAIN] ✅ {len(threads)} services started\n")

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[MAIN] ⛔ Interrupted — shutting down")
        sys.exit(0)
