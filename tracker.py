import discord
from discord import Embed
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests, json, os
from dotenv import load_dotenv
import traceback
import math

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

STATS_CHANNELS_FILE = "./stats_channels.json"

def load_stats_channel_ids():
    if os.path.exists(STATS_CHANNELS_FILE):
        with open(STATS_CHANNELS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_stats_channel_ids(data):
    with open(STATS_CHANNELS_FILE, "w") as f:
        json.dump(data, f, indent=2)

stats_channel_ids = load_stats_channel_ids()

async def update_stats_channels(guild):
    category_name = "📊 PVE Tarkov Stats"
    category = discord.utils.get(guild.categories, name=category_name)

    if not category:

        BOT_ROLE_ID = 1388899865861292127
            
        bot_role = guild.get_role(BOT_ROLE_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
            bot_role: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
        }
        category = await guild.create_category(category_name, overwrites=overwrites)
        print(f"📁 Created category '{category_name}'")

    total_kd = total_lvl = total_sr = count = 0

    for discord_id, user_data in user_config.items():
        player_id = user_data["player_id"]
        try:
            data = fetch_data(player_id)
            exp = data["info"].get("experience", 0)
            level = calculate_level_from_experience(exp)
            pmc_raids = get_counter(data, ["Sessions", "Pmc"])
            survived = get_counter(data, ["ExitStatus", "Survived", "Pmc"])
            kills = get_counter(data, ["Kills"])
            deaths = get_counter(data, ["Deaths"])

            kd_ratio = kills / deaths if deaths else 0
            sr_ratio = (survived / pmc_raids) * 100 if pmc_raids else 0

            total_kd += kd_ratio
            total_lvl += level
            total_sr += sr_ratio
            count += 1
        except Exception as e:
            print(f"❌ Failed to process player {player_id}: {e}")
            continue
        
    if count == 0:
        avg_kd = avg_lvl = avg_sr = 0
    else:
        avg_kd = total_kd / count
        avg_lvl = total_lvl / count
        avg_sr = total_sr / count


    channel_names = {
        "kd": f"🔫 Avg K/D: {avg_kd:.2f}",
        "lvl": f"🎖 Avg Level: {avg_lvl:.1f}",
        "sr": f"🏃 Avg S/R: {avg_sr:.1f}%",
        "tracked": f"📦 PVE Profiles: {count}"
    }

    for key, name in channel_names.items():
        channel_id = stats_channel_ids.get(key)
        channel = guild.get_channel(channel_id) if channel_id else None
    
        if not channel:
            # Delete miscategorized or missing channels
            if channel:
                await channel.delete()

            if bot_role is None:
                print(f"❌ Bot role with ID {BOT_ROLE_ID} not found in guild {guild.name}")
                return

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
                bot_role: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
            }

            new_channel = await guild.create_voice_channel(name=name, category=category, overwrites=overwrites)
            stats_channel_ids[key] = new_channel.id

            save_stats_channel_ids(stats_channel_ids)
        else:
            try:
                await channel.edit(name=name)
            except discord.Forbidden:
                print(f"❌ Missing permission to edit channel {channel.name} ({channel.id})")
            except Exception as e:
                print(f"❌ Unexpected error editing channel {channel.id}: {e}")

def format_embed(data, diff, player_id, previous=None):
    def annotate_change(current, previous_val):
        if previous_val is None:
            return f"{current:,.2f}" if isinstance(current, float) else f"{current:,}"

        delta = current - previous_val
        if delta == 0:
            return f"{current:,.2f}" if isinstance(current, float) else f"{current:,}"

        sign = "+" if delta > 0 else "-"
        if isinstance(current, float):
            return f"{current:,.2f} ({sign}{abs(delta):,.2f})"
        else:
            return f"{current:,} ({sign}{abs(delta):,})"

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

    # For diffs in overall embed
    prev_exp = previous["info"]["experience"] if previous else None
    prev_kills = get_counter(previous, ["Kills"]) if previous else None
    prev_deaths = get_counter(previous, ["Deaths"]) if previous else None
    prev_survived = get_counter(previous, ["ExitStatus", "Survived", "Pmc"]) if previous else None
    prev_raids = get_counter(previous, ["Sessions", "Pmc"]) if previous else None
    prev_played = previous.get("pmcStats", {}).get("eft", {}).get("totalInGameTime", 0) if previous else None
    prev_played_hrs = prev_played / 3600 if prev_played else None
    prev_streak = get_counter(previous, ["LongestWinStreak", "Pmc"]) if previous else None
    prev_achievements = len(previous.get("achievements", {})) if previous else None
    prev_level = calculate_level_from_experience(prev_exp) if prev_exp is not None else None
    prev_kd = (prev_kills / prev_deaths) if prev_kills is not None and prev_deaths and prev_deaths > 0 else None
    prev_sr = (prev_survived / prev_raids) * 100 if prev_survived is not None and prev_raids else None

    updated_embed = Embed(
        title="📊 Updated Tarkov Stats",
        description=f"\n[{name}](https://tarkov.dev/players/pve/{player_id}) \nSide: {side}",
        color=0x00ff99
    )
    updated_embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/5354/5354526.png")

    updated_embed.add_field(name="PMC Level", value=f"```{annotate_change(level, prev_level)}```", inline=False)

    if diff["experience"]:
        d = diff["experience"]
        updated_embed.add_field(
            name="Experience",
            value=f"```{d['from']:,} → {d['to']:,} (+{d['diff']:,})```",
            inline=False
        )
    else:
        updated_embed.add_field(
            name="Experience",
            value=f"```{exp:,} (no change)```",
            inline=False
        )

    updated_embed.add_field(name="Achievements", value=f"```{annotate_change(achievements, prev_achievements)}```", inline=True)
    updated_embed.add_field(name="PMC Raids", value=f"```{annotate_change(pmc_raids, prev_raids)}```", inline=True)
    updated_embed.add_field(name="Survived", value=f"```{annotate_change(survived, prev_survived)}```", inline=True)
    updated_embed.add_field(name="Kills", value=f"```{annotate_change(kills, prev_kills)}```", inline=True)
    updated_embed.add_field(name="Deaths", value=f"```{annotate_change(deaths, prev_deaths)}```", inline=True)
    updated_embed.add_field(name="K/D Ratios", value=f"```{annotate_change(kd_ratio, prev_kd)}```", inline=True)
    updated_embed.add_field(name="S/R Ratio", value=f"```{annotate_change(sr_ratio, prev_sr)}```", inline=True)
    updated_embed.add_field(name="Time Played (hrs)", value=f"```{annotate_change(time_played_hrs, prev_played_hrs)}```", inline=True)

    if diff["skills"]:
        filtered_changes = [
            s for s in diff["skills"]
            if int(s["from"] // 100) != int(s["to"] // 100)
        ]

        if filtered_changes:
            sorted_changes = sorted(filtered_changes, key=lambda s: s["diff"], reverse=True)[:5]
            skill_lines = [
                f"• {s['id']}: Level {int(s['from'] // 100)} → {int(s['to'] // 100)} (+{int(s['to'] // 100 - s['from'] // 100)})"
                for s in sorted_changes
            ]
            updated_embed.add_field(name="🧠 Top Skill Changes", value=f"```{chr(10).join(skill_lines)}```", inline=False)
        else:
            updated_embed.add_field(name="🧠 Top Skill Changes", value="```No skill level changes```", inline=False)

    if diff["mastery"]:
        filtered_mastery = [
            m for m in diff["mastery"]
            if int(m["from"]) != int(m["to"])
        ]

        if filtered_mastery:
            sorted_changes = sorted(filtered_changes, key=lambda m: m["diff"], reverse=True)[:5]
            mastery_lines = [
                f"• {m['id']}: EXP {int(m['from'])} → {int(m['to'])} (+{int(m['to'] - m['from'])})"
                for m in filtered_mastery
            ]
            updated_embed.add_field(name="🔫 Weapon Mastery Changes", value=f"```{chr(10).join(mastery_lines)}```", inline=False)
        else:
            updated_embed.add_field(name="🔫 Weapon Mastery Changes", value="```No weapon mastery level changes```", inline=False)

    updated_embed.set_footer(text="Tracked via PVE Stats Tracker and Tarkov.Dev")

    # ▶️ Overall Embed
    overall_embed = Embed(
        title=f"📘 Overall PVE Tarkov Stats for {name}",
        color=0x6666ff
    )
    overall_embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/5354/5354526.png")

    overall_embed.add_field(name="PMC Level", value=f"```{level}```", inline=False)
    overall_embed.add_field(name="Experience", value=f"```{exp}```", inline=True)
    overall_embed.add_field(name="Achievements", value=f"```{achievements}```", inline=True)
    overall_embed.add_field(name="PMC Raids", value=f"```{pmc_raids}```", inline=True)
    overall_embed.add_field(name="Survived", value=f"```{survived}```", inline=True)
    overall_embed.add_field(name="K/D Ratio", value=f"```{kd_ratio:.2f}```", inline=True)
    overall_embed.add_field(name="S/R Ratio", value=f"```{sr_ratio:.2f}```", inline=True)
    overall_embed.add_field(name="Longest Win Streak", value=f"```{annotate_change(win_streak, prev_streak)}```", inline=True)
    
    all_skills = data.get("skills", {}).get("Common", [])
    if all_skills:
        top_skills = sorted(all_skills, key=lambda s: s["Progress"], reverse=True)[:5]
        skills_text = "\n".join([
            f"{s['Id']}: Level {int(s['Progress'] // 100)}"
            for s in top_skills
        ])
        overall_embed.add_field(name="🏅 Top Skills", value=f"```{skills_text}```", inline=False)

    overall_embed.set_footer(text="Snapshot from PVE Stats Tracker and Tarkov.Dev")

    return updated_embed, overall_embed

async def daily_task():
    print("🔁 Running daily stat check...")

    for discord_id, data in user_config.items():
        player_id = data["player_id"]
        try:
            latest = fetch_data(player_id)
            snapshot_file = get_snapshot_file(player_id)

            user = await bot.fetch_user(discord_id)

            if os.path.exists(snapshot_file):
                with open(snapshot_file, "r") as f:
                    previous = json.load(f)
                
                prev_updated = previous.get("updated")
                latest_updated = latest.get("updated")

                if prev_updated == latest_updated:
                    print(f"📭 No new update for {player_id}.")
                    continue
            else:
                # No previous snapshot, save and notify
                with open(snapshot_file, "w") as f:
                    json.dump(latest, f, indent=2)
                await user.send("✅ Initial Tarkov stat snapshot saved.")
                continue


            diff = diff_stats(latest, previous)
            updated_embed, overall_embed = format_embed(latest, diff, player_id, previous)

            await user.send(embeds=[updated_embed, overall_embed])

            with open(snapshot_file, "w") as f:
                json.dump(latest, f, indent=2)
            
            user_config[discord_id]["last_notified"] = latest_updated
            save_user_config()

        except Exception as e:
            print(f"❌ Failed for user {discord_id}: {e}")
            traceback.print_exc()

async def statChannels():
    print("🔁 Running stat channels check...")
    TARGET_GUILD_ID = 972229559233695814
    target_guild = bot.get_guild(TARGET_GUILD_ID)
    if target_guild:
        print(f"📊 Setting up stat channels in guild: {target_guild.name}")
        await update_stats_channels(target_guild)
    else:
        print("⚠️ Target guild not found. Make sure the bot is in the correct server.")


@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    scheduler.add_job(daily_task, 'interval', hours=3)  # Set to every 24 hours
    scheduler.add_job(statChannels, 'interval', hours=3)  # Set to every 6 hours
    scheduler.start()
    print("⏰ Scheduler started.")
    print("▶️ Running daily_task immediately...")
    await daily_task()
    await statChannels()

@bot.command(name="track")
async def track(ctx, url: str):
    try:
        # Validate and extract player ID from the provided URL
        if not url.startswith("https://tarkov.dev/players/pve/"):
            guide_msg = (
                "❌ **Invalid link format.**\n\n"
                "🧭 To track your Tarkov stats:\n"
                "1. Go to **<https://tarkov.dev/players?gameMode=pve>**\n"
                "2. Search for your name or someone else's\n"
                "3. Copy the full player URL (e.g. `https://tarkov.dev/players/pve/9571121`)\n"
                "4. Use this command again: `!track <url>`"
            )
            await ctx.send(guide_msg)
            return


        player_id = url.split("/")[-1]
        if not player_id.isdigit():
            await ctx.send("❌ Couldn't extract a valid player ID from the URL.")
            return

        discord_id = str(ctx.author.id)

        # 🔒 Prevent overwrite
        if discord_id in user_config:
            await ctx.send(f"⚠️ You are already tracking a player. Use `!untrack` first if you'd like to track someone else.")
            return

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

        # 📊 Create embed
        diff = diff_stats(latest, latest)  # No change yet
        updated_embed, overall_embed = format_embed(latest, diff, player_id)

        # 📩 Send DM
        user = await bot.fetch_user(ctx.author.id)
        await user.send(f"✅ You're now tracking **{latest['info'].get('nickname', 'Unknown')}** (ID: `{player_id}`) — here’s your current snapshot:")
        await user.send(embeds=[updated_embed, overall_embed])

        # ✅ Let them know in server channel
        await ctx.send(f"📬 <@{ctx.author.id}>, I’ve sent your stats via DM.")

        # ✅ Save to user_config
        user_config[discord_id] = {
            "player_id": player_id,
            "last_notified": latest.get("updated")
        }
        save_user_config()

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