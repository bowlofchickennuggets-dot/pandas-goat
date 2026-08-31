# Discord Token Bot - Railway (English Version)

Discord bot for retrieving Nakama session tokens (Animal Company).

**🔥 FEATURES:**
- ✅ Bot + Token Refresh run in parallel
- ✅ Tokens auto-refresh every 2 minutes
- ✅ **15-minute cooldown per user** (anti-spam)
- ✅ Better error handling and logging
- ✅ No more crashes

---

## ⚙️ Railway Setup

### 1. Replace files in GitHub

Your repo already exists. Just replace these files:
- `main.py` ← UPDATED
- `token_bot.py` ← UPDATED (cooldown system added)
- `refresh_token.py` ← UPDATED (English)
- `Dockerfile` ← Same
- `cooldowns.json` ← NEW (auto-created)

Or delete the old repo and create a new one with these files.

### 2. Configure environment variable

In Railway → Your Project → **Variables**:

```
DISCORD_BOT_TOKEN = your_token_here
```

⚠️ **Replace `your_token_here` with your actual Discord bot token**

### 3. Deploy

Railway auto-detects the `Dockerfile` and deploys automatically.

---

## 📋 Files

- **main.py** - Entry point, runs bot + refresh in parallel
- **token_bot.py** - Discord bot with `/token` command (includes 15-min cooldown)
- **refresh_token.py** - Auto-refresh loop (every 2 minutes)
- **tokens.json** - Token storage
- **cooldowns.json** - User cooldown tracking (auto-created)
- **Dockerfile** - Railway deployment config
- **requirements.txt** - Python dependencies

---

## ✅ Expected Output

In **Railway → Console** you should see:

```
============================================================
🚀 DISCORD BOT + TOKEN REFRESH
============================================================
[MAIN] Starting Discord bot...
[MAIN] Starting token refresher...
[MAIN] ✅ Bot and refresher started

[BOT] Starting Discord bot...
============================================================
✅ Bot connected as: YourBot#1234
✅ /token command available (15-min cooldown per user)
============================================================

[REFRESH] 🔄 AUTO TOKEN REFRESHER - NAKAMA
============================================================
[REFRESH] 🔁 Loop mode active (every 120s)
[REFRESH] ⏱️ Token expires in 12345s
[REFRESH] 💤 Sleeping for 120s...
[REFRESH] 🔄 Refreshing tokens...
[REFRESH] ✅ Token refreshed successfully!
```

---

## 🔧 Key Improvements

1. **Problem:** Bot and refresher didn't run together
   **Solution:** `main.py` executes both in parallel threads

2. **Problem:** Tokens didn't auto-refresh
   **Solution:** `refresh_token.py --loop` runs continuously

3. **Problem:** Users could spam the `/token` command
   **Solution:** 15-minute per-user cooldown with JSON tracking

4. **Problem:** Confusing logs
   **Solution:** Clear prefixes: `[BOT]`, `[REFRESH]`, `[MAIN]`

5. **Problem:** Unhandled errors
   **Solution:** Improved try-except with traceback

---

## 🎮 How to Use (For Your Users)

Simply type `/token` in Discord to get your session tokens.

**Cooldown:** You can use the command once every **15 minutes**.

If you try to use it before the cooldown expires, you'll see:
```
⏱️ Cooldown Active
You can use this command again in: 10m 45s
(15-minute cooldown per user)
```

---

## 📞 Troubleshooting

1. Verify `DISCORD_BOT_TOKEN` is set in Railway → Variables
2. Check logs in Railway → Console
3. Look for errors with `[ERROR]` or `❌` prefix
4. Ensure your Discord bot token is valid
5. Restart the deployment if needed

---

## 💡 Pro Tips

- **Railway free tier** goes to sleep after 30 minutes of inactivity
- Consider switching to **Fly.io** (free 24/7) or paying $7/month for Railway
- Cooldowns are stored in `cooldowns.json` and persist across restarts
- All responses are ephemeral (private, only you see them)

---

**Ready to deploy!** 🚀
