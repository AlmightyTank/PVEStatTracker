import discord
from discord import Embed
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests, json, os
from dotenv import load_dotenv
import traceback

ENV_FILE = "./.env"

load_dotenv(dotenv_path=ENV_FILE, override=True)  # Exact path
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

CONFIG_FILE = "./user_config.json"

def load_user_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_user_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(user_config, f, indent=2)

user_config = load_user_config()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

XP_LEVELS = [
    0, 1000, 4017, 8432, 14256, 21477, 30023, 39936, 51204, 63723,
    77563, 92713, 111881, 134674, 161139, 191417, 225194, 262366, 302484, 345751,
    391649, 440444, 492366, 547896, 609066, 679255, 755444, 837672, 925976, 1020396,
    1120969, 1227735, 1344260, 1470605, 1606833, 1759965, 1923579, 2097740, 2282513, 2477961,
    2684149, 2901143, 3132824, 3379281, 3640603, 3929436, 4233995, 4554372, 4890662, 5242956,
    5611348, 5995931, 6402287, 6830542, 7280825, 7753260, 8247975, 8765097, 9304752, 9876880,
    10512365, 11193911, 11929835, 12727177, 13615989, 14626588, 15864243, 17555001, 19926895,
    22926895, 26526895, 30726895, 35526895, 40926895, 46926895, 53526895, 60726895, 69126895,
    81126895
]

def get_snapshot_file(player_id):
    os.makedirs("./snapshots", exist_ok=True)
    path = f"./snapshots/{player_id}_snapshot.json"

    # Create the file if it doesn't exist
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f, indent=2)

    return path


def fetch_data(player_id):
    url = f"https://players.tarkov.dev/pve/{player_id}.json"
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def calculate_level_from_experience(exp):
    for i in range(len(XP_LEVELS) - 1, -1, -1):
        if exp >= XP_LEVELS[i]:
            return i + 1
    return 1

def get_counter(data, key_path):
    for item in data.get("pmcStats", {}).get("eft", {}).get("overAllCounters", {}).get("Items", []):
        if item["Key"] == key_path:
            return item["Value"]
    return 0

def diff_stats(current, previous):
    result = {"experience": None, "skills": [], "mastery": []}
    if current["info"]["experience"] != previous["info"]["experience"]:
        result["experience"] = {
            "from": previous["info"]["experience"],
            "to": current["info"]["experience"],
            "diff": current["info"]["experience"] - previous["info"]["experience"]
        }

    prev_skills = {s["Id"]: s["Progress"] for s in previous["skills"]["Common"]}
    for skill in current["skills"]["Common"]:
        sid = skill["Id"]
        if sid in prev_skills and skill["Progress"] != prev_skills[sid]:
            result["skills"].append({
                "id": sid,
                "from": prev_skills[sid],
                "to": skill["Progress"],
                "diff": skill["Progress"] - prev_skills[sid]
            })

    prev_mastery = {m["Id"]: m["Progress"] for m in previous["skills"]["Mastering"]}
    for mastery in current["skills"]["Mastering"]:
        mid = mastery["Id"]
        if mid in prev_mastery and mastery["Progress"] != prev_mastery[mid]:
            result["mastery"].append({
                "id": mid,
                "from": prev_mastery[mid],
                "to": mastery["Progress"],
                "diff": mastery["Progress"] - prev_mastery[mid]
            })

    return result

def format_embed(data, diff, player_id):
    name = data["info"].get("nickname", "Unknown")
    exp = data["info"].get("experience", 0)
    level = calculate_level_from_experience(exp)
    side = data["info"].get("side", "Unknown")
    time_played_secs = data.get("pmcStats", {}).get("eft", {}).get("totalInGameTime", 0)
    time_played_hrs = time_played_secs / 3600

    pmc_raids = get_counter(data, ["Sessions", "Pmc"])
    survived = get_counter(data, ["ExitStatus", "Survived", "Pmc"])
    kills = get_counter(data, ["Kills"])
    deaths = get_counter(data, ["Deaths"])
    kd_ratio = kills / deaths if deaths else 0
    sr_ratio = (survived / pmc_raids) * 100 if pmc_raids else 0
    achievements = len(data.get("achievements", {}))
    win_streak = get_counter(data, ["LongestWinStreak", "Pmc"])

    updated_embed = Embed(
        title="📊 Updated Tarkov Stats",
        description=f"[{name}](https://tarkov.dev/players/pve/{player_id})",
        color=0x00ff99
    )
    updated_embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/5354/5354526.png")

    updated_embed.add_field(name="PMC Level", value=f"**```{str(level)}```**", inline=True)
    updated_embed.add_field(name="Side", value=f"**```{side}```**", inline=True)

    if diff["experience"]:
        d = diff["experience"]
        updated_embed.add_field(
            name="⭐ Experience",
            value=f"**```{d['from']:,} → {d['to']:,} (+{d['diff']:,})```**",
            inline=False
        )
    else:
        updated_embed.add_field(
            name="⭐ Experience",
            value=f"**```{exp:,} (no change)```**",
            inline=False
        )

    if diff["skills"]:
        sorted_changes = sorted(diff["skills"], key=lambda s: s["diff"], reverse=True)[:5]
        skill_lines = [
            f"• {s['id']}: Level {(s['from']/100):.0f} → {(s['to']/100):.0f} (+{(s['diff']/100):.0f})"
            for s in sorted_changes
        ]
        updated_embed.add_field(name="🧠 Top Skill Changes", value=f"**```{chr(10).join(skill_lines)}```**", inline=False)
    else:
        updated_embed.add_field(name="🧠 Top Skill Changes", value="**```No skill changes```**", inline=False)

    if diff["mastery"]:
        mastery_lines = [
            f"• {m['id']}: {m['from']} → {m['to']} (+{m['diff']})"
            for m in diff["mastery"]
        ]
        updated_embed.add_field(name="🔫 Weapon Mastery Changes", value=f"**```{chr(10).join(mastery_lines)}```**", inline=False)
    else:
        updated_embed.add_field(name="🔫 Weapon Mastery Changes", value="**```No weapon mastery changes```**", inline=False)

    updated_embed.set_footer(text="Tracked via Tarkov.Dev")

    overall_embed = Embed(
        title=f"📘 Overall Tarkov Stats for {name}",
        color=0x6666ff
    )
    overall_embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/5354/5354526.png")

    overall_embed.add_field(name="PMC Level", value=f"**```{str(level)}```**", inline=True)
    overall_embed.add_field(name="Side", value=f"**```{side}```**", inline=True)
    overall_embed.add_field(name="Experience", value=f"**```{exp:,}```**", inline=True)
    overall_embed.add_field(name="Achievements", value=f"**```{str(achievements)}```**", inline=True)
    overall_embed.add_field(name="PMC Raids", value=f"**```{str(pmc_raids)}```**", inline=True)
    overall_embed.add_field(name="Survived", value=f"**```{str(survived)}```**", inline=True)
    overall_embed.add_field(name="Kills", value=f"**```{str(kills)}```**", inline=True)
    overall_embed.add_field(name="Deaths", value=f"**```{str(deaths)}```**", inline=True)
    overall_embed.add_field(name="K/D Ratio", value=f"**```{kd_ratio:.2f}```**", inline=True)
    overall_embed.add_field(name="S/R Ratio", value=f"**```{sr_ratio:.2f}%```**", inline=True)
    overall_embed.add_field(name="Time Played (hrs)", value=f"**```{time_played_hrs:.2f}```**", inline=True)
    overall_embed.add_field(name="Longest Win Streak", value=f"**```{str(win_streak)}```**", inline=True)

    all_skills = data.get("skills", {}).get("Common", [])
    top_skills = sorted(all_skills, key=lambda s: s["Progress"], reverse=True)[:5]
    if top_skills:
        skills_text = "\n".join([f"{s['Id']}: Level {(s['Progress']/100):.0f}" for s in top_skills])
        overall_embed.add_field(name="🏅 Top Skills", value=f"**```{skills_text}```**", inline=False)

    overall_embed.set_footer(text="Snapshot from Tarkov.Dev")

    return updated_embed, overall_embed

async def daily_task():
    print("🔁 Running daily stat check...")
    updated_data = requests.get("https://players.tarkov.dev/profile/updated.json").json()

    for discord_id, data in user_config.items():
        player_id = data["player_id"]
        last_sent = data.get("last_notified")

        last_updated = updated_data.get(player_id)
        if not last_updated:
            print(f"⚠️ No update time for player {player_id}, skipping...")
            continue

        if last_sent == last_updated:
            print(f"📭 Already sent stats for {player_id} today.")
            continue

        try:
            latest = fetch_data(player_id)
            snapshot_file = get_snapshot_file(player_id)

            if os.path.exists(snapshot_file):
                with open(snapshot_file, "r") as f:
                    previous = json.load(f)
            else:
                previous = None

            user = await bot.fetch_user(discord_id)

            if not previous:
                with open(snapshot_file, "w") as f:
                    json.dump(latest, f, indent=2)
                await user.send("✅ Initial Tarkov stat snapshot saved.")
                continue

            diff = diff_stats(latest, previous)
            updated_embed, overall_embed = format_embed(latest, diff, player_id)

            await user.send(embeds=[updated_embed, overall_embed])

            with open(snapshot_file, "w") as f:
                json.dump(latest, f, indent=2)
            
            user_config[discord_id]["last_notified"] = last_updated
            save_user_config()

        except Exception as e:
            print(f"❌ Failed for user {discord_id}: {e}")
            traceback.print_exc()

@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    scheduler.add_job(daily_task, 'interval', hours=24)  # Set to every 24 hours
    scheduler.start()
    print("⏰ Scheduler started.")
    print("▶️ Running daily_task immediately...")
    await daily_task()

@bot.command(name="track")
async def track(ctx, nickname: str):
    try:
        index_data = requests.get("https://players.tarkov.dev/profile/index.json").json()

        # Find player_id where nickname matches
        player_id = next((pid for pid, name in index_data.items() if name.lower() == nickname.lower()), None)

        if not player_id:
            await ctx.send(f"❌ Player nickname '{nickname}' not found.")
            return

        updated_data = requests.get("https://players.tarkov.dev/profile/updated.json").json()
        last_updated = updated_data.get(player_id)

        if not last_updated:
            await ctx.send(f"⚠️ Could not determine last update time for player ID `{player_id}`.")
            return

        discord_id = str(ctx.author.id)

        # 🔒 Prevent overwrite
        if discord_id in user_config:
            await ctx.send(f"⚠️ You are already tracking a player. Use `!untrack` first if you'd like to track someone else.")
            return

        # ✅ Save to user_config
        user_config[discord_id] = {
            "player_id": player_id,
            "last_notified": last_updated
        }
        save_user_config()

        # 📦 Fetch latest snapshot and save it
        latest = fetch_data(player_id)
        snapshot_file = get_snapshot_file(player_id)
        with open(snapshot_file, "w") as f:
            json.dump(latest, f, indent=2)

        # 📊 Create embed
        diff = diff_stats(latest, latest)  # No change yet
        updated_embed, overall_embed = format_embed(latest, diff, player_id)

        # 📩 Send DM
        user = await bot.fetch_user(ctx.author.id)
        await user.send(f"✅ You're now tracking **{nickname}** (ID: `{player_id}`) — here's a snapshot of your current stats:")
        await user.send(embeds=[updated_embed, overall_embed])

        # ✅ Let them know in server channel
        await ctx.send(f"📬 <@{ctx.author.id}>, I’ve sent your stats for **{nickname}** via DM.")

    except Exception as e:
        await ctx.send(f"❌ Error during tracking: {e}")
        traceback.print_exc()

@bot.command(name="untrack")
async def untrack(ctx):
    discord_id = str(ctx.author.id)

    if discord_id in user_config:
        # Get tracked player ID and nickname
        tracked_player_id = user_config[discord_id]["player_id"]
        nickname = "Unknown"

        try:
            index_data = requests.get("https://players.tarkov.dev/profile/index.json").json()
            nickname = index_data.get(tracked_player_id, "Unknown")
        except:
            pass

        # Delete snapshot file if it exists
        snapshot_path = get_snapshot_file(tracked_player_id)
        if os.path.exists(snapshot_path):
            os.remove(snapshot_path)

        # Remove from config and save
        del user_config[discord_id]
        save_user_config()

        await ctx.send(f"❌ You have stopped tracking **{nickname}**, and the snapshot was deleted, <@{ctx.author.id}>.")
    else:
        await ctx.send(f"⚠️ You are not currently tracking that player - **{nickname}**.")

bot.run(DISCORD_TOKEN)