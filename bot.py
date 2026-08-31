import os
import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------
# Intent Setup & Bot Initialization
# ---------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Parse Guild ID from Environment
RAW_GUILD_IDS = os.getenv("ALLOWED_GUILD_IDS", "")
print(f"[BOT] 🔎 Raw ALLOWED_GUILD_IDS env: '{RAW_GUILD_IDS}'")

try:
    ALLOWED_GUILD_IDS = [int(gid.strip()) for gid in RAW_GUILD_IDS.split(",") if gid.strip()]
    print(f"[BOT] 🔎 Parsed ALLOWED_GUILD_IDS: {ALLOWED_GUILD_IDS}")
except ValueError:
    ALLOWED_GUILD_IDS = []
    print("[BOT] ⚠️ Warning: Failed to parse ALLOWED_GUILD_IDS.")

# ---------------------------------------------------------
# Slash Commands
# ---------------------------------------------------------
@bot.tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 `{round(bot.latency * 1000)}ms`")

@bot.tree.command(name="token", description="Get active tokens from pool")
async def token(interaction: discord.Interaction):
    await interaction.response.send_message("Token request received! Check your direct messages.", ephemeral=True)

# ---------------------------------------------------------
# Event Handlers
# ---------------------------------------------------------
@bot.event
async def on_ready():
    print("[BOT] Starting unified bot...")
    print(f"[BOT] Logged in as {bot.user} (ID: {bot.user.id})")
    
    if ALLOWED_GUILD_IDS:
        for guild_id in ALLOWED_GUILD_IDS:
            guild_obj = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild_obj)
            try:
                synced = await bot.tree.sync(guild=guild_obj)
                print(f"[BOT] ✅ Successfully synced {len(synced)} command(s) to Guild ID: {guild_id}")
            except Exception as e:
                print(f"[BOT] ❌ Failed to sync commands to Guild {guild_id}: {e}")
    else:
        try:
            synced = await bot.tree.sync()
            print(f"[BOT] ✅ Successfully synced {len(synced)} global command(s).")
        except Exception as e:
            print(f"[BOT] ❌ Failed to sync global commands: {e}")

# ---------------------------------------------------------
# Run Bot
# ---------------------------------------------------------
if __name__ == "__main__":
    BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN environment variable is missing.")
    
    bot.run(BOT_TOKEN)
