import os
import sqlite3
import aiohttp
import discord

from pathlib import Path
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

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "linked_keys.db"))

API_BASE = "https://key-system-api.luaisgame.workers.dev/api"
OWNER_API = f"{API_BASE}/owner"

MAX_CREATE_AMOUNT = 25

if not TOKEN:
    raise ValueError("DISCORD_TOKEN missing")

if not OWNER_KEY:
    raise ValueError("OWNER_KEY missing")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS linked_keys_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            key TEXT UNIQUE NOT NULL,
            class_type TEXT DEFAULT 'Unknown',
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='linked_keys'
    """)

    old_exists = cur.fetchone()

    if old_exists:
        cur.execute("PRAGMA table_info(linked_keys)")
        columns = [col[1] for col in cur.fetchall()]

        if "id" not in columns:
            cur.execute("""
                INSERT OR IGNORE INTO linked_keys_new
                (user_id, key, class_type, claimed_at)
                SELECT
                    user_id,
                    key,
                    'Unknown',
                    CURRENT_TIMESTAMP
                FROM linked_keys
            """)

            cur.execute("DROP TABLE linked_keys")
            cur.execute("ALTER TABLE linked_keys_new RENAME TO linked_keys")
        else:
            cur.execute("DROP TABLE linked_keys_new")
    else:
        cur.execute("ALTER TABLE linked_keys_new RENAME TO linked_keys")

    con.commit()
    con.close()


def get_user_keys(user_id: int):
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    cur.execute(
        """
        SELECT key, class_type, claimed_at
        FROM linked_keys
        WHERE user_id = ?
        ORDER BY claimed_at DESC
        """,
        (str(user_id),)
    )

    rows = cur.fetchall()
    con.close()
    return rows


def is_key_claimed(key: str):
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    cur.execute("SELECT user_id FROM linked_keys WHERE key = ?", (key,))
    row = cur.fetchone()

    con.close()
    return row is not None


def link_key(user_id: int, key: str, class_type: str):
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO linked_keys (user_id, key, class_type)
        VALUES (?, ?, ?)
        """,
        (str(user_id), key, class_type)
    )

    con.commit()
    con.close()


def is_staff(member: discord.Member):
    return any(role.id == STAFF_ROLE_ID for role in member.roles)


def is_owner(user: discord.User):
    return user.id in OWNER_DISCORD_IDS


def success_embed(title, description):
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green()
    )


def error_embed(title, description):
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.red()
    )


async def api_post(url: str, payload: dict):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            try:
                data = await response.json()
            except Exception:
                data = {
                    "valid": False,
                    "message": await response.text()
                }

            return response.status, data


@bot.event
async def on_ready():
    init_db()

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync error: {e}")

    print(f"Database path: {DB_PATH}")
    print(f"Logged in as {bot.user}")


@app_commands.choices(
    class_type=[
        app_commands.Choice(name="Premium", value="Premium"),
        app_commands.Choice(name="Staff", value="Staff"),
        app_commands.Choice(name="Tester", value="Tester"),
        app_commands.Choice(name="Developer", value="Developer"),
    ]
)
@bot.tree.command(name="createkey", description="Create one or more keys")
async def createkey(
    interaction: discord.Interaction,
    class_type: app_commands.Choice[str],
    amount: app_commands.Range[int, 1, MAX_CREATE_AMOUNT] = 1
):
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            embed=error_embed("Error", "Use this inside a server."),
            ephemeral=True
        )
        return

    if not is_staff(interaction.user):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You cannot create keys."),
            ephemeral=True
        )
        return

    if class_type.value == "Developer" and not is_owner(interaction.user):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You cannot create Developer keys."),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)

    created_keys = []
    failed = 0

    for _ in range(amount):
        status, data = await api_post(
            f"{OWNER_API}/create",
            {
                "ownerKey": OWNER_KEY,
                "classType": class_type.value
            }
        )

        if status == 200 and data.get("valid") and data.get("key"):
            created_keys.append(data["key"])
        else:
            failed += 1

    if not created_keys:
        await interaction.followup.send(
            embed=error_embed("Key Creation Failed", "No keys were created.")
        )
        return

    embed = success_embed(
        f"✅ Created {len(created_keys)} Key{'s' if len(created_keys) != 1 else ''}",
        f"```{chr(10).join(created_keys)}```"
    )

    embed.add_field(name="Type", value=class_type.value, inline=True)
    embed.add_field(name="Created By", value=interaction.user.mention, inline=True)

    if failed:
        embed.add_field(name="Failed", value=str(failed), inline=True)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="listkeys", description="List all keys")
async def listkeys(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "Only the bot owner can list keys."),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{OWNER_API}/list",
        {"ownerKey": OWNER_KEY}
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("List Failed", data.get("message", "Could not list keys.")),
            ephemeral=True
        )
        return

    keys = [x for x in data.get("keys", []) if not x.get("owner")]

    if not keys:
        await interaction.followup.send(
            embed=error_embed("No Keys", "No keys found."),
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
    chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)]

    for i, chunk in enumerate(chunks, start=1):
        embed = discord.Embed(
            title=f"📋 Key List {i}/{len(chunks)}",
            description=chunk,
            color=discord.Color.blurple()
        )

        await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="redeem", description="Link yourself to a key")
async def redeem(interaction: discord.Interaction, key: str):
    await interaction.response.defer(ephemeral=True)

    key = key.strip()

    if is_key_claimed(key):
        await interaction.followup.send(
            embed=error_embed("Already Redeemed", "That key is already linked to a Discord user."),
            ephemeral=True
        )
        return

    status, data = await api_post(
        f"{OWNER_API}/list",
        {"ownerKey": OWNER_KEY}
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Redeem Failed", "Could not verify this key."),
            ephemeral=True
        )
        return

    found = None

    for entry in data.get("keys", []):
        if entry.get("key") == key and not entry.get("owner"):
            found = entry
            break

    if not found:
        await interaction.followup.send(
            embed=error_embed("Invalid Key", "That key does not exist."),
            ephemeral=True
        )
        return

    class_type = found.get("classType", "Unknown")

    try:
        link_key(interaction.user.id, key, class_type)
    except sqlite3.IntegrityError:
        await interaction.followup.send(
            embed=error_embed("Already Redeemed", "That key is already claimed."),
            ephemeral=True
        )
        return

    embed = success_embed(
        "✅ Key Redeemed",
        "Your Discord account has claimed this key."
    )

    embed.add_field(name="Key", value=f"`{key}`", inline=False)
    embed.add_field(name="Type", value=class_type, inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="mykeys", description="List all keys you redeemed")
async def mykeys(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    keys = get_user_keys(interaction.user.id)

    if not keys:
        await interaction.followup.send(
            embed=error_embed("No Redeemed Keys", "You have not redeemed any keys."),
            ephemeral=True
        )
        return

    lines = []

    for key, class_type, claimed_at in keys:
        lines.append(
            f"`{key}`\nType: **{class_type}**\nClaimed: `{claimed_at}`"
        )

    text = "\n\n".join(lines)
    chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)]

    for i, chunk in enumerate(chunks, start=1):
        embed = discord.Embed(
            title=f"🔑 Your Redeemed Keys {i}/{len(chunks)}",
            description=chunk,
            color=discord.Color.blurple()
        )

        embed.set_footer(text=f"Total keys: {len(keys)}")

        await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="resethwid", description="Reset HWID on one of your redeemed keys")
async def resethwid(interaction: discord.Interaction, key: str = None):
    await interaction.response.defer(ephemeral=True)

    keys = get_user_keys(interaction.user.id)

    if not keys:
        await interaction.followup.send(
            embed=error_embed("No Linked Key", "Use `/redeem` first."),
            ephemeral=True
        )
        return

    if key is None:
        if len(keys) == 1:
            key = keys[0][0]
        else:
            await interaction.followup.send(
                embed=error_embed(
                    "Multiple Keys Found",
                    "Use `/mykeys`, then run `/resethwid key:YOUR_KEY`."
                ),
                ephemeral=True
            )
            return

    owned_keys = [row[0] for row in keys]

    if key not in owned_keys:
        await interaction.followup.send(
            embed=error_embed("Not Your Key", "You can only reset keys you redeemed."),
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
            embed=error_embed(
                "HWID Reset Failed",
                data.get("message", "You may be on cooldown.")
            ),
            ephemeral=True
        )
        return

    embed = success_embed(
        "✅ HWID Reset",
        "Your HWID has been reset successfully."
    )

    embed.add_field(name="Key", value=f"`{key}`", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


bot.run(TOKEN)
