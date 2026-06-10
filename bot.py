import os
import aiohttp
import discord

from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_KEY = os.getenv("OWNER_KEY")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env")

if not OWNER_KEY:
    raise ValueError("OWNER_KEY not found in .env")

API_BASE = "https://v0-key-system-validation.vercel.app/owner"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Sync error: {e}")

    print(f"Logged in as {bot.user}")


@app_commands.choices(
    class_type=[
        app_commands.Choice(name="Developer", value="Developer"),
        app_commands.Choice(name="Premium", value="Premium"),
        app_commands.Choice(name="Staff", value="Staff"),
        app_commands.Choice(name="Tester", value="Tester"),
    ]
)
@bot.tree.command(
    name="createkey",
    description="Create a new key"
)
async def createkey(
    interaction: discord.Interaction,
    class_type: app_commands.Choice[str]
):
    await interaction.response.defer(ephemeral=True)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE}/create",
                json={
                    "ownerKey": OWNER_KEY,
                    "classType": class_type.value
                }
            ) as response:
                data = await response.json()

        print("========== CREATE RESPONSE ==========")
        print(data)
        print("=====================================")

        await interaction.followup.send(
            f"```json\n{data}\n```",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error:\n```{e}```",
            ephemeral=True
        )


@bot.tree.command(
    name="listkeys",
    description="List all keys"
)
async def listkeys(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE}/list",
                json={
                    "ownerKey": OWNER_KEY
                }
            ) as response:
                data = await response.json()

        print("========== LIST RESPONSE ==========")
        print(data)
        print("===================================")

        if not data.get("valid"):
            await interaction.followup.send(
                "❌ Invalid owner key.",
                ephemeral=True
            )
            return

        keys = data.get("keys", [])

        if not keys:
            await interaction.followup.send(
                "No keys found.",
                ephemeral=True
            )
            return

        output = []

        for entry in keys:
            if entry.get("owner"):
                continue

            key = entry.get("key", "Unknown")
            class_type = entry.get("classType", "Unknown")
            hwid = entry.get("hwid")

            output.append(
                f"🔑 `{key}` | {class_type} | HWID: {hwid or 'None'}"
            )

        text = "\n".join(output)

        if len(text) <= 1900:
            await interaction.followup.send(
                text,
                ephemeral=True
            )
        else:
            chunks = [
                text[i:i + 1900]
                for i in range(0, len(text), 1900)
            ]

            await interaction.followup.send(
                chunks[0],
                ephemeral=True
            )

            for chunk in chunks[1:]:
                await interaction.followup.send(
                    chunk,
                    ephemeral=True
                )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error:\n```{e}```",
            ephemeral=True
        )


bot.run(TOKEN)
