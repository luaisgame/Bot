import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BACKEND_URL   = os.getenv("BACKEND_URL", "http://localhost:3000").rstrip("/")

# ── Bot setup ────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ── Helper ───────────────────────────────────────────────────────────────────

async def call_backend(
    asset_type: str,
    ids: list[int],
    place_id: int,
) -> list[dict]:
    payload = {
        "assetType": asset_type,
        "ids":       ids,
        "placeId":   place_id,
    }
    async with aiohttp.ClientSession() as session:
        # POST kicks off the job — backend returns 200 immediately, processes async
        async with session.post(
            f"{BACKEND_URL}/reupload",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Backend returned HTTP {resp.status}: {text}")

        # Poll GET / until the backend says "done"
        # Each poll returns [{oldId, newId}, ...] for completed items
        results: list[dict] = []
        POLL_INTERVAL = 2    # seconds
        MAX_WAIT      = 600  # 10 minutes

        for _ in range(MAX_WAIT // POLL_INTERVAL):
            await asyncio.sleep(POLL_INTERVAL)

            async with session.get(
                f"{BACKEND_URL}/",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status != 200:
                    continue
                text = (await r.text()).strip()

            if not text:
                continue
            if text == "done":
                break

            try:
                items = json.loads(text)
                results.extend(items)
            except Exception:
                pass
        else:
            raise asyncio.TimeoutError()

    return results

def build_embed(results: list[dict], asset_type: str, ids: list[int]) -> discord.Embed:
    # results is [{oldId, newId}, ...]
    successful = {str(item["oldId"]): item["newId"] for item in results}

    sent_ids = {str(i) for i in ids}
    failed   = {id_: "not returned by backend" for id_ in sent_ids if id_ not in successful}

    total = len(ids)
    ok    = len(successful)
    fail  = len(failed)

    color = discord.Color.green() if fail == 0 else (
        discord.Color.red() if ok == 0 else discord.Color.orange()
    )

    embed = discord.Embed(
        title=f"🔄 {asset_type} Reupload Results",
        color=color,
    )
    embed.set_footer(text=f"{ok}/{total} succeeded")

    if successful:
        lines = [f"`{old}` → `{new}`" for old, new in list(successful.items())[:20]]
        if len(successful) > 20:
            lines.append(f"… and {len(successful) - 20} more")
        embed.add_field(
            name=f"✅ Successful ({ok})",
            value="\n".join(lines),
            inline=False,
        )

    if failed:
        lines = [f"`{id_}` — {reason[:80]}" for id_, reason in list(failed.items())[:10]]
        if len(failed) > 10:
            lines.append(f"… and {len(failed) - 10} more")
        embed.add_field(
            name=f"❌ Failed ({fail})",
            value="\n".join(lines),
            inline=False,
        )

    return embed

def parse_ids(raw: str) -> list[int]:
    """Parse a space or comma separated string of asset IDs into a list of ints."""
    tokens = raw.replace(",", " ").split()
    ids = []
    for t in tokens:
        t = t.strip()
        if not t.isdigit():
            raise ValueError(f"`{t}` is not a valid asset ID")
        ids.append(int(t))
    if not ids:
        raise ValueError("No asset IDs provided")
    return ids

# ── Slash commands ───────────────────────────────────────────────────────────

@bot.tree.command(name="reupload", description="Reupload Roblox assets to your account or group")
@app_commands.describe(
    asset_type  = "Type of asset to reupload",
    ids         = "Asset IDs separated by spaces or commas",
    place_id    = "Your Roblox place ID",
)
@app_commands.choices(asset_type=[
    app_commands.Choice(name="Animation", value="Animation"),
    app_commands.Choice(name="Sound", value="Sound"),
    app_commands.Choice(name="Mesh", value="Mesh"),
])
async def reupload(
    interaction: discord.Interaction,
    asset_type:  app_commands.Choice[str],
    ids:         str,
    place_id:    int,
):
    await interaction.response.defer(thinking=True)

    try:
        id_list = parse_ids(ids)
    except ValueError as e:
        await interaction.followup.send(f"❌ **Invalid IDs:** {e}", ephemeral=True)
        return

    if len(id_list) > 200:
        await interaction.followup.send(
            "❌ Max 200 IDs per request. Split them into smaller batches.", ephemeral=True
        )
        return

    # Check backend is alive (GET / returns 200)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{BACKEND_URL}/", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    raise ConnectionError()
    except Exception:
        await interaction.followup.send(
            "❌ **Backend is not running.** Start `assetreuploader` first then try again.",
            ephemeral=True,
        )
        return

    try:
        results = await call_backend(
            asset_type=asset_type.value,
            ids=id_list,
            place_id=place_id,
        )
    except asyncio.TimeoutError:
        await interaction.followup.send("❌ **Timed out** — the backend took too long to respond.", ephemeral=True)
        return
    except RuntimeError as e:
        await interaction.followup.send(f"❌ **Backend error:** {e}", ephemeral=True)
        return
    except Exception as e:
        await interaction.followup.send(f"❌ **Unexpected error:** {e}", ephemeral=True)
        return

    embed = build_embed(results, asset_type.value, id_list)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="status", description="Check if the reuploader backend is running")
async def status(interaction: discord.Interaction):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{BACKEND_URL}/", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    await interaction.response.send_message(
                        f"✅ Backend is **online** at `{BACKEND_URL}`", ephemeral=True
                    )
                    return
    except Exception:
        pass
    await interaction.response.send_message(
        f"❌ Backend is **offline** — make sure `assetreuploader` is running.", ephemeral=True
    )

# ── Events ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})\"")
    print(f"Backend URL: {BACKEND_URL}")
    print("Slash commands synced. Ready.")

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN is not set.\n"
            "Add it to your .env file:  DISCORD_TOKEN=your_token_here"
        )
    bot.run(DISCORD_TOKEN)
