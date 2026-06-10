import os
import json
import secrets
import string

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

KEYS_FILE = "keys.json"

# Create file if it doesn't exist
if not os.path.exists(KEYS_FILE):
    with open(KEYS_FILE, "w") as f:
        json.dump([], f)

def load_keys():
    with open(KEYS_FILE, "r") as f:
        return json.load(f)

def save_keys(keys):
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=4)

def generate_key(length=20):
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))

intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(e)

    print(f"Logged in as {bot.user}")

@bot.tree.command(name="createkey", description="Create a new key")
async def createkey(interaction: discord.Interaction):
    key = generate_key()

    keys = load_keys()
    keys.append(key)
    save_keys(keys)

    await interaction.response.send_message(
        f"✅ Key created: `{key}`",
        ephemeral=True
    )

@bot.tree.command(name="listkeys", description="List all keys")
async def listkeys(interaction: discord.Interaction):
    keys = load_keys()

    if not keys:
        await interaction.response.send_message(
            "No keys found.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "\n".join(f"`{k}`" for k in keys),
        ephemeral=True
    )

bot.run(TOKEN)
