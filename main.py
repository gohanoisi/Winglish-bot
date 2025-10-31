import discord
from discord.ext import commands
from config import DISCORD_TOKEN
from db import init_db
from utils import main_menu_view, info_embed

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class WinglishBot(commands.Bot):
    async def setup_hook(self):
        # 起動時にDB初期化
        await init_db()
        # COG読み込み
        await self.load_extension("cogs.onboarding")
        await self.load_extension("cogs.menu")
        await self.load_extension("cogs.vocab")
        await self.load_extension("cogs.svocm")
        await self.load_extension("cogs.reading")
        # 永続View（BAM）
        self.add_view(main_menu_view())

bot = WinglishBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    # 管理チャンネル等に起動通知したければここで

@bot.tree.command(name="start", description="Winglishを開始（個人鍵チャンネルにメニューを出します）")
async def start_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    # 個人鍵チャンネルへメニュー（onboarding側で作成済み）
    await interaction.followup.send("あなたの個人チャンネルにメニューを送ります。", ephemeral=True)

bot.run(DISCORD_TOKEN)
