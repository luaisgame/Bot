import os
import aiohttp
import discord

from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
OWNER_KEY = os.getenv("OWNER_KEY", "").strip()

OWNER_DISCORD_IDS = {
    int(x.strip())
    for x in os.getenv("OWNER_DISCORD_IDS", "").split(",")
    if x.strip().isdigit()
}

CREATE_ROLE_ID = 1458539044014391306
MAX_CREATE_AMOUNT = 25

API_BASE = "https://luaisgame.com/api"
OWNER_API = f"{API_BASE}/owner"

if not TOKEN:
    raise ValueError("DISCORD_TOKEN missing")

if not OWNER_KEY:
    raise ValueError("OWNER_KEY missing")

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


def is_owner(user: discord.User):
    return user.id in OWNER_DISCORD_IDS


def has_create_role(member: discord.Member):
    return any(role.id == CREATE_ROLE_ID for role in member.roles)


def success_embed(title, description):
    return discord.Embed(title=title, description=description, color=discord.Color.green())


def error_embed(title, description):
    return discord.Embed(title=title, description=description, color=discord.Color.red())


async def api_post(url: str, payload: dict):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            text = await response.text()

            try:
                data = await response.json()
            except Exception:
                data = {"valid": False, "message": text}

            print("API URL:", url)
            print("API STATUS:", response.status)
            print("API RESPONSE:", data)

            return response.status, data


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync error: {e}")

    print("=" * 50)
    print("BOT STARTED")
    print("User:", bot.user)
    print("API:", API_BASE)
    print("OWNER IDS:", OWNER_DISCORD_IDS)
    print("OWNER KEY:", repr(OWNER_KEY))
    print("=" * 50)


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
    quantity: app_commands.Range[int, 1, MAX_CREATE_AMOUNT] = 1
):
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            embed=error_embed("Error", "Use this command inside a server."),
            ephemeral=True
        )
        return

    if not has_create_role(interaction.user):
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

    created = []
    errors = []

    for _ in range(quantity):
        status, data = await api_post(
            f"{OWNER_API}/create",
            {
                "ownerKey": OWNER_KEY,
                "classType": class_type.value
            }
        )

        if status == 200 and data.get("valid") and data.get("key"):
            created.append(data["key"])
        else:
            errors.append(str(data))

    if not created:
        await interaction.followup.send(
            embed=error_embed(
                "Key Creation Failed",
                f"No keys were created.\n```{chr(10).join(errors)[:3000]}```"
            )
        )
        return

    embed = success_embed(
        f"✅ Created {len(created)} Key{'s' if len(created) != 1 else ''}",
        f"```{chr(10).join(created)}```"
    )

    embed.add_field(name="Type", value=class_type.value, inline=True)
    embed.add_field(name="Quantity", value=str(len(created)), inline=True)
    embed.add_field(name="Created By", value=interaction.user.mention, inline=True)

    if errors:
        embed.add_field(name="Failed", value=str(len(errors)), inline=True)

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
            embed=error_embed("List Failed", str(data)),
            ephemeral=True
        )
        return

    keys = [k for k in data.get("keys", []) if not k.get("owner")]

    if not keys:
        await interaction.followup.send(
            embed=error_embed("No Keys", "No keys found."),
            ephemeral=True
        )
        return

    lines = []

    for k in keys:
        lines.append(
            f"`{k.get('key', 'Unknown')}`\n"
            f"Type: **{k.get('classType', 'Unknown')}** | "
            f"HWID: `{k.get('hwid') or 'None'}`"
        )

    text = "\n\n".join(lines)
    chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)]

    for i, chunk in enumerate(chunks, start=1):
        await interaction.followup.send(
            embed=discord.Embed(
                title=f"📋 Keys {i}/{len(chunks)}",
                description=chunk,
                color=discord.Color.blurple()
            ),
            ephemeral=True
        )


@bot.tree.command(name="redeem", description="Claim a key")
async def redeem(interaction: discord.Interaction, key: str):
    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{API_BASE}/redeem",
        {
            "key": key.strip(),
            "userId": str(interaction.user.id)
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Redeem Failed", data.get("message", "Invalid key.")),
            ephemeral=True
        )
        return

    await interaction.followup.send(
        embed=success_embed(
            "✅ Key Redeemed",
            f"Key: `{data.get('key')}`\nType: **{data.get('classType')}**"
        ),
        ephemeral=True
    )


@bot.tree.command(name="mykeys", description="List your redeemed keys")
async def mykeys(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{API_BASE}/mykeys",
        {"userId": str(interaction.user.id)}
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Failed", data.get("message", "Could not load keys.")),
            ephemeral=True
        )
        return

    keys = data.get("keys", [])

    if not keys:
        await interaction.followup.send(
            embed=error_embed("No Keys", "You have not redeemed any keys."),
            ephemeral=True
        )
        return

    text = "\n\n".join(
        f"`{k.get('key')}`\nType: **{k.get('classType', 'Unknown')}**"
        for k in keys
    )

    chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)]

    for i, chunk in enumerate(chunks, start=1):
        await interaction.followup.send(
            embed=discord.Embed(
                title=f"🔑 Your Keys {i}/{len(chunks)}",
                description=chunk,
                color=discord.Color.blurple()
            ),
            ephemeral=True
        )


@bot.tree.command(name="resethwid", description="Reset HWID on one of your keys")
async def resethwid(interaction: discord.Interaction, key: str):
    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{API_BASE}/reset",
        {
            "ownerKey": OWNER_KEY,
            "key": key.strip(),
            "userId": str(interaction.user.id)
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Reset Failed", data.get("message", "Could not reset HWID.")),
            ephemeral=True
        )
        return

    await interaction.followup.send(
        embed=success_embed("✅ HWID Reset", f"Reset HWID for:\n`{key}`"),
        ephemeral=True
    )


@bot.tree.command(name="keyinfo", description="Show info about a key")
async def keyinfo(interaction: discord.Interaction, key: str):
    if not is_owner(interaction.user):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "Only the bot owner can use this."),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{OWNER_API}/keyinfo",
        {
            "ownerKey": OWNER_KEY,
            "key": key.strip()
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Not Found", data.get("message", "Key not found.")),
            ephemeral=True
        )
        return

    k = data.get("keyData", {})
    redeemed = data.get("redeemed")

    embed = discord.Embed(title="🔎 Key Info", color=discord.Color.blurple())
    embed.add_field(name="Key", value=f"`{k.get('key', key)}`", inline=False)
    embed.add_field(name="Type", value=k.get("classType", "Unknown"), inline=True)
    embed.add_field(name="HWID", value=f"`{k.get('hwid') or 'None'}`", inline=True)

    if redeemed:
        embed.add_field(name="Redeemed By", value=f"<@{redeemed.get('userId')}>", inline=False)
    else:
        embed.add_field(name="Redeemed", value="No", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="deletekey", description="Delete a key")
async def deletekey(interaction: discord.Interaction, key: str):
    if not is_owner(interaction.user):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "Only the bot owner can delete keys."),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{OWNER_API}/delete",
        {
            "ownerKey": OWNER_KEY,
            "key": key.strip()
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Delete Failed", data.get("message", "Could not delete key.")),
            ephemeral=True
        )
        return

    await interaction.followup.send(
        embed=success_embed("✅ Key Deleted", f"Deleted:\n`{key}`"),
        ephemeral=True
    )


@bot.tree.command(name="uploadscript", description="Upload or update a Luau script")
async def uploadscript(
    interaction: discord.Interaction,
    name: str,
    file: discord.Attachment
):
    if not is_owner(interaction.user):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "Only the bot owner can upload scripts."),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    if not file.filename.lower().endswith((".lua", ".luau", ".txt")):
        await interaction.followup.send(
            embed=error_embed("Invalid File", "Upload a `.lua`, `.luau`, or `.txt` file."),
            ephemeral=True
        )
        return

    content_bytes = await file.read()

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = content_bytes.decode("utf-8", errors="replace")

    status, data = await api_post(
        f"{OWNER_API}/uploadscript",
        {
            "ownerKey": OWNER_KEY,
            "name": name.strip().lower(),
            "content": content
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Upload Failed", data.get("message", "Could not upload script.")),
            ephemeral=True
        )
        return

    await interaction.followup.send(
        embed=success_embed(
            "✅ Script Uploaded",
            f"Name: `{name.strip().lower()}`\nEndpoint: `{API_BASE}/getscript`"
        ),
        ephemeral=True
    )


@bot.tree.command(name="apitest", description="Test the key API")
async def apitest(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "Only the bot owner can test the API."),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{OWNER_API}/list",
        {"ownerKey": OWNER_KEY}
    )

    await interaction.followup.send(
        embed=discord.Embed(
            title="API Test",
            description=f"Status: `{status}`\n```{str(data)[:3500]}```",
            color=discord.Color.blurple()
        ),
        ephemeral=True
    )


bot.run(TOKEN)
