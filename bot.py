from builtins import print
import os
import base64
from pickle import TRUE
import aiohttp
import discord
import asyncio

from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands

load_dotenv()

TOKEN = os.getenv("Bot_Token")
OWNER_KEY = os.getenv("MoonVeil_Api")
MOONVEIL_API_TOKEN = os.getenv("Owner_Key")

STAFF_ROLE_ID = 1458539044014391306
DEV_ROLE_ID = 1458539079577899088

GUILD_ID = 1458535933090726205

API_BASE = "https://luaisgame.com/api"
OWNER_API = f"{API_BASE}/owner"

if not TOKEN:
    raise ValueError("DISCORD_TOKEN missing")

if not OWNER_KEY:
    raise ValueError("OWNER_KEY missing")

intents = discord.Intents.default()
intents.guilds = True
intents.dm_messages = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    allowed_contexts=app_commands.AppCommandContext(
        guild=True,
        dm_channel=True,
        private_channel=True,
    ),
    allowed_installs=app_commands.AppInstallationType(
        guild=True,
        user=True,
    ),
)

async def has_role(bot: discord.Client, user_id: int, role_id: int) -> bool:
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return False

    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.NotFound:
            return False
        except discord.Forbidden:
            return False

    return any(role.id == role_id for role in member.roles)


async def has_dev_role(bot: discord.Client, user_id: int) -> bool:
    return await has_role(bot, user_id, DEV_ROLE_ID)

async def has_staff_role(bot: discord.Client, user_id: int) -> bool:
    return await has_role(bot, user_id, STAFF_ROLE_ID)

async def require_dev(interaction: discord.Interaction) -> bool:
    return await has_dev_role(interaction.client, interaction.user.id)

async def require_staff_or_dev(interaction: discord.Interaction) -> bool:
    return (
        await has_dev_role(interaction.client, interaction.user.id)
        or await has_staff_role(interaction.client, interaction.user.id)
    )

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
    print("DEV_ROLE_ID:", DEV_ROLE_ID)
    print("OWNER_KEY:", repr(OWNER_KEY))
    print("MOONVEIL_API:", MOONVEIL_API_TOKEN)
    print("=" * 50)


@app_commands.choices(
    class_type=[
        app_commands.Choice(name="Premium", value="Premium"),
        app_commands.Choice(name="Staff", value="Staff"),
        app_commands.Choice(name="Tester", value="Tester"),
        app_commands.Choice(name="Developer", value="Developer"),
        app_commands.Choice(name="Custom", value="Custom"),
    ]
)
@bot.tree.command(name="createkey", description="Create one or more keys")
async def createkey(
    interaction: discord.Interaction,
    class_type: app_commands.Choice[str],
    quantity: app_commands.Range[int, 1, 10000] = 1,
    customkey: str | None = None,
):
    if not await require_staff_or_dev(interaction):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You need developer permissions."),
            ephemeral=True
        )
        return
    if (
        class_type.value == "Developer"
        and not await has_dev_role(interaction.client, interaction.user.id)
    ):
        await interaction.response.send_message(
            embed=error_embed(
                "No Permission",
                "Only developers can create Developer keys."
            ),
            ephemeral=True
        )
        return
    

    status, data = await api_post(
        f"{OWNER_API}/create",
        {
            "ownerKey": OWNER_KEY,
            "classType": class_type.value,
            "quantity": quantity,
            "customKey": customkey
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Failed", data.get("message", "No keys were created."))
        )
        return

    created = data.get("keys") or []
    if not created and data.get("key"):
        created = [data["key"]]

    if not created:
        await interaction.followup.send(
            embed=error_embed("Failed", "API returned no keys.")
        )
        return
    
    await interaction.response.defer(ephemeral=False)

    embed = success_embed(
        f"✅ Created {len(created)} Key{'s' if len(created) != 1 else ''}",
        f"```{chr(10).join(created)}```"
    )

    embed.add_field(name="Type", value=class_type.value, inline=True)
    embed.add_field(name="Quantity", value=str(len(created)), inline=True)
    embed.add_field(name="Created By", value=interaction.user.mention, inline=True)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="listkeys", description="List all keys")
async def listkeys(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not await require_dev(interaction):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You need developer permissions."),
            ephemeral=True
        )
        return    

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

    text = "\n\n".join(
        f"`{k.get('key', 'Unknown')}`\nType: **{k.get('classType', 'Unknown')}** | HWID: `{k.get('hwid') or 'None'}`"
        for k in keys
    )

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
            f"Key: `{data.get('key')}`\nType: **{data.get('classType', 'Unknown')}**"
        ),
        ephemeral=True
    )
@bot.tree.command(name="spam")
async def spam(interaction: discord.Interaction):
    await interaction.response.send_message("Starting...", ephemeral=True)

    for i in range(9999):
        await interaction.followup.send("hiiii")
        await asyncio.sleep(0.01)
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

    await interaction.followup.send(
        embed=discord.Embed(
            title="🔑 Your Keys",
            description=text[:4000],
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
    await interaction.response.defer(ephemeral=True)
    if not await require_dev(interaction):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You need developer permissions."),
            ephemeral=True
        )
        return

    

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
    await interaction.response.defer(ephemeral=True)
    if not await require_dev(interaction):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You need developer permissions."),
            ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=False)

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
        ephemeral=False
    )


@bot.tree.command(name="uploadscript", description="Upload or update a Luau script")
async def uploadscript(
    interaction: discord.Interaction,
    name: str,
    file: discord.Attachment
):
    if not await require_dev(interaction):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You need developer permissions."),
            ephemeral=True
        )
        return

    if not file.filename.lower().endswith((".lua", ".luau", ".txt")):
        await interaction.followup.send(
            embed=error_embed("Invalid File", "Upload a `.lua`, `.luau`, or `.txt` file."),
            ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=False)

    content_bytes = await file.read()
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
        ephemeral=False
    )
@bot.tree.command(name="uploadscriptandobfuscate", description="Upload or update a Luau script")
async def uploadscriptandobfuscate(
    interaction: discord.Interaction,
    name: str,
    file: discord.Attachment
):  
    await interaction.response.defer(ephemeral=True)
    if not await require_dev(interaction):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You need developer permissions."),
            ephemeral=True
        )
        return

    if not file.filename.lower().endswith((".lua", ".luau", ".txt")):
        await interaction.followup.send(
            embed=error_embed("Invalid File", "Upload a `.lua`, `.luau`, or `.txt` file."),
            ephemeral=True
        )
        return

    content_bytes = await file.read()
    content = content_bytes.decode("utf-8", errors="replace")

    async def post(url, payload, headers):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers
            ) as response:
                return await response.text()


    response = await post(
        "https://moonveil.cc/api/v2/obf",
        {   
            "options": {
                "cffDecompose": True,
                "cffMangleGlobals": True,
                "cffMangleNext": True,
                "cffMangleStrings": True
            },
            "script": content
        },
        {
            "Authorization": f"Bearer { MOONVEIL_API_TOKEN }"
        }
    )

    status, data = await api_post(
        f"{OWNER_API}/uploadscript",
        {
            "ownerKey": OWNER_KEY,
            "name": name.strip().lower(),
            "content": response
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


@bot.tree.command(name="uploadfile", description="Upload a downloadable file")
async def uploadfile(
    interaction: discord.Interaction,
    name: str,
    file: discord.Attachment
):
    if not await require_staff_or_dev(interaction):
        await interaction.response.send_message(
            embed=error_embed("No Permission", "You need developer permissions."),
            ephemeral=True
        )
        return

    content = await file.read()
    content_base64 = base64.b64encode(content).decode("utf-8")

    status, data = await api_post(
        f"{OWNER_API}/uploadfile",
        {
            "ownerKey": OWNER_KEY,
            "name": name.strip().lower(),
            "filename": file.filename,
            "mimeType": file.content_type or "application/octet-stream",
            "contentBase64": content_base64
        }
    )

    if status != 200 or not data.get("valid"):
        await interaction.followup.send(
            embed=error_embed("Upload Failed", data.get("message", "Could not upload file.")),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)

    await interaction.followup.send(
        embed=success_embed(
            "✅ File Uploaded",
            f"```{data.get('url')}```"
        ),
        ephemeral=False
    )


@bot.tree.command(name="apitest", description="Test the validation API")
async def apitest(interaction: discord.Interaction):
    if not await require_dev(interaction):
        await interaction.response.send_message(
            embed=error_embed(
                "No Permission",
                "You need developer permissions."
            ),
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    status, data = await api_post(
        f"{API_BASE}/validate",
        {
            "key": OWNER_KEY,
            "hwid": "API_TEST"
        }
    )

    await interaction.followup.send(
        embed=discord.Embed(
            title="🧪 API Validation Test",
            description=(
                f"Endpoint: `{API_BASE}/validate`\n"
                f"Status: `{status}`\n\n"
                f"```json\n{str(data)[:3000]}\n```"
            ),
            color=discord.Color.blurple()
        ),
        ephemeral=False
    )

bot.run(TOKEN)
