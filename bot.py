import os
import sqlite3
import aiohttp
import discord

from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_KEY = os.getenv("OWNER_KEY")
OWNER_DISCORD_IDS = {
    int(x.strip())
    for x in os.getenv("OWNER_DISCORD_IDS", "").split(",")
    if x.strip().isdigit()
}

STAFF_ROLE_ID = 1458539044014391306

API_BASE = "https://v0-key-system-validation.vercel.app/api"
OWNER_API = f"{API_BASE}/owner"

if not TOKEN:
    raise ValueError("DISCORD_TOKEN missing from .env")

if not OWNER_KEY:
    raise ValueError("OWNER_KEY missing from .env")


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def init_db():
    con = sqlite3.connect("linked_keys.db")
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS linked_keys (
            user_id TEXT PRIMARY KEY,
            key TEXT UNIQUE NOT NULL
        )
    """)

    con.commit()
    con.close()


def get_linked_key(user_id: int):
    con = sqlite3.connect("linked_keys.db")
    cur = con.cursor()

    cur.execute(
        "SELECT key FROM linked_keys WHERE user_id = ?",
        (str(user_id),)
    )

    row = cur.fetchone()
    con.close()

    return row[0] if row else None


def link_key(user_id: int, key: str):
    con = sqlite3.connect("linked_keys.db")
    cur = con.cursor()

    cur.execute(
        "INSERT INTO linked_keys (user_id, key) VALUES (?, ?)",
        (str(user_id), key)
    )

    con.commit()
    con.close()


def is_staff(member: discord.Member):
    return any(role.id == STAFF_ROLE_ID for role in member.roles)


def is_owner(user: discord.User):
    return user.id in OWNER_DISCORD_IDS


def embed_success(title: str, description: str):
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green()
    )
    return embed


def embed_error(title: str, description: str):
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.red()
    )
    return embed


async def api_post(url: str, payload: dict):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            text = await response.text()

            try:
                return response.status, await response.json()
            except Exception:
                return response.status, {
                    "valid": False,
                    "message": text
                }


@bot.event
async def on_ready():
    init_db()

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Sync error: {e}")

    print(f"Logged in as {bot.user}")


@app_commands.choices(
    class_type=[
        app_commands.Choice(name="Premium", value="Premium"),
        app_commands.Choice(name="Staff", value="Staff"),
        app_commands.Choice(name="Tester", value="Tester"),
        app_commands.Choice(name="Developer", value="Developer"),
    ]
)
@bot.tree.command(name="createkey", description="Create a new key")
async def createkey(
    interaction: discord.Interaction,
    class_type: app_commands.Choice[str]
):
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            embed=embed_error("Error", "This command can only be used in a server."),
            ephemeral=True
        )
        return

    if not is_staff(interaction.user):
        await interaction.response.send_message(
            embed=embed_error("No Permission", "You do not have permission to create keys."),
            ephemeral=True
        )
        return

    if class_type.value == "Developer" and not is_owner(interaction.user):
        await interaction.response.send_message(
            embed=embed_error("No Permission", "You cannot create Developer keys."),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)

    status, data = await api_post(
        f"{OWNER_API}/create",
        {
            "ownerKey": OWNER_KEY,
            "classType": class_type.value
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=embed_error("Key Creation Failed", "The owner key was rejected or the API failed.")
        )
        return

    key = data.get("key", "Unknown")

    embed = embed_success(
        "Key Created",
        f"```{key}```"
    )

    embed.add_field(name="Type", value=class_type.value, inline=True)
    embed.add_field(name="Created By", value=interaction.user.mention, inline=True)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="listkeys", description="List all keys")
async def listkeys(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        await interaction.response.send_message(
            embed=embed_error("No Permission", "Only the bot owner can list keys."),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{OWNER_API}/list",
        {
            "ownerKey": OWNER_KEY
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=embed_error("List Failed", "Could not list keys."),
            ephemeral=True
        )
        return

    keys = [
        x for x in data.get("keys", [])
        if not x.get("owner")
    ]

    if not keys:
        await interaction.followup.send(
            embed=embed_error("No Keys", "No normal keys were found."),
            ephemeral=True
        )
        return

    lines = []

    for entry in keys:
        key = entry.get("key", "Unknown")
        class_type = entry.get("classType", "Unknown")
        hwid = entry.get("hwid") or "None"

        lines.append(f"`{key}`\nType: **{class_type}** | HWID: `{hwid}`")

    text = "\n\n".join(lines)

    chunks = [
        text[i:i + 3500]
        for i in range(0, len(text), 3500)
    ]

    for index, chunk in enumerate(chunks, start=1):
        embed = discord.Embed(
            title=f"Key List Page {index}/{len(chunks)}",
            description=chunk,
            color=discord.Color.blurple()
        )

        await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="redeem", description="Link yourself to a key")
async def redeem(interaction: discord.Interaction, key: str):
    await interaction.response.defer(ephemeral=True)

    key = key.strip()

    existing = get_linked_key(interaction.user.id)

    if existing:
        await interaction.followup.send(
            embed=embed_error(
                "Already Linked",
                f"You are already linked to:\n```{existing}```"
            ),
            ephemeral=True
        )
        return

    status, data = await api_post(
        f"{OWNER_API}/list",
        {
            "ownerKey": OWNER_KEY
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=embed_error("Redeem Failed", "Could not verify this key."),
            ephemeral=True
        )
        return

    all_keys = data.get("keys", [])

    found = None

    for entry in all_keys:
        if entry.get("key") == key and not entry.get("owner"):
            found = entry
            break

    if not found:
        await interaction.followup.send(
            embed=embed_error("Invalid Key", "That key does not exist."),
            ephemeral=True
        )
        return

    try:
        link_key(interaction.user.id, key)
    except sqlite3.IntegrityError:
        await interaction.followup.send(
            embed=embed_error("Already Redeemed", "That key is already linked to another Discord user."),
            ephemeral=True
        )
        return

    embed = embed_success(
        "Key Redeemed",
        "Your Discord account has been linked to this key."
    )

    embed.add_field(name="Key", value=f"`{key}`", inline=False)
    embed.add_field(name="Type", value=found.get("classType", "Unknown"), inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="resethwid", description="Reset the HWID on your linked key")
async def resethwid(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    key = get_linked_key(interaction.user.id)

    if not key:
        await interaction.followup.send(
            embed=embed_error(
                "No Linked Key",
                "Use `/redeem` first to link yourself to a key."
            ),
            ephemeral=True
        )
        return

    status, data = await api_post(
        f"{API_BASE}/reset",
        {
            "key": key,
            "hwid": None
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=embed_error(
                "HWID Reset Failed",
                data.get("message", "You may be on cooldown.")
            ),
            ephemeral=True
        )
        return

    embed = embed_success(
        "HWID Reset",
        "Your HWID has been reset successfully."
    )

    embed.add_field(name="Key", value=f"`{key}`", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


bot.run(TOKEN)
