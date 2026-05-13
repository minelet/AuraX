import re
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # FIX WARNING
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("partners.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS partners (
    user_id INTEGER,
    link TEXT UNIQUE
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS partner_points (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 0
)
""")

conn.commit()

# =========================
# LEADERBOARD STORAGE
# =========================
leaderboard_message_id = None
leaderboard_channel_id = None

# =========================
# UTIL
# =========================
def extract_invite(text):
    match = re.search(r"(https?:\/\/)?(www\.)?(discord\.gg|discord\.com\/invite)\/[A-Za-z0-9]+", text)
    return match.group(0) if match else None

def is_admin(member: discord.Member):
    return member.guild_permissions.administrator or any(
        role.name in ["Founder", "Administrator"] for role in member.roles
    )

# =========================
# LEADERBOARD FUNCTIONS
# =========================
async def get_leaderboard_text():
    c.execute("SELECT user_id, points FROM partner_points ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()

    if not rows:
        return "No partners yet."

    msg = "🏆 Leaderboard:\n"

    for i, (uid, pts) in enumerate(rows, 1):
        try:
            user = await bot.fetch_user(uid)
            name = user.name
        except:
            name = f"User {uid}"

        msg += f"{i}. {name} - {pts}\n"

    return msg

async def update_leaderboard():
    global leaderboard_message_id, leaderboard_channel_id

    if not leaderboard_message_id or not leaderboard_channel_id:
        return

    channel = bot.get_channel(leaderboard_channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(leaderboard_message_id)
    except:
        return

    new_text = await get_leaderboard_text()
    await message.edit(content=new_text)

# =========================
# MODAL
# =========================
class PartnerModal(discord.ui.Modal, title="Submit Partner Ad"):

    message = discord.ui.TextInput(
        label="Paste FULL partner message",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        msg = self.message.value
        invite = extract_invite(msg)

        if not invite:
            await interaction.followup.send("❌ No valid invite found.", ephemeral=True)
            return

        member = interaction.user
        admin = isinstance(member, discord.Member) and is_admin(member)

        if not admin:
            c.execute("SELECT 1 FROM partners WHERE link=?", (invite,))
            if c.fetchone():
                await interaction.followup.send("⚠️ This link was already partnered.", ephemeral=True)
                return

        c.execute(
            "INSERT OR IGNORE INTO partners (user_id, link) VALUES (?,?)",
            (interaction.user.id, invite)
        )

        c.execute("""
            INSERT INTO partner_points (user_id, points)
            VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET points = points + 1
        """, (interaction.user.id,))

        conn.commit()

        await interaction.channel.send(msg)

        await interaction.followup.send(
            f"✅ +1 partner point for {interaction.user.mention}",
            ephemeral=True
        )

        # 🔥 AUTO UPDATE
        await update_leaderboard()

# =========================
# COMMANDS
# =========================
@bot.tree.command(name="partner", description="Submit partner message")
async def partner(interaction: discord.Interaction):
    await interaction.response.send_modal(PartnerModal())

@bot.tree.command(name="partners_view", description="Check partner points")
async def partners_view(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user

    c.execute("SELECT points FROM partner_points WHERE user_id=?", (target.id,))
    row = c.fetchone()
    points = row[0] if row else 0

    await interaction.response.send_message(f"{target.name} has {points} partner points")

@bot.tree.command(name="partners_points_change", description="Set partner points (Admin only)")
async def partners_points_change(interaction: discord.Interaction, user: discord.User, amount: int):

    member = interaction.user
    if not isinstance(member, discord.Member) or not is_admin(member):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return

    c.execute("""
        INSERT INTO partner_points (user_id, points)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET points = excluded.points
    """, (user.id, amount))

    conn.commit()

    await interaction.response.send_message(
        f"✅ Set {user.name}'s points to {amount}",
        ephemeral=True
    )

    # 🔥 AUTO UPDATE
    await update_leaderboard()

@bot.tree.command(name="partner_top", description="Leaderboard")
async def partner_top(interaction: discord.Interaction):
    global leaderboard_message_id, leaderboard_channel_id

    text = await get_leaderboard_text()

    await interaction.response.send_message(text)
    msg = await interaction.original_response()

    leaderboard_message_id = msg.id
    leaderboard_channel_id = interaction.channel.id

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
