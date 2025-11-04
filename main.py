# main.py
import logging
import sys
from typing import Any

try:
    import discord
    from discord.ext import commands
except ImportError:
    print("❌ discord.py がインストールされていません。`pip install -r requirements.txt` を実行してください。")
    sys.exit(1)

from config import DISCORD_TOKEN
from db import init_db
from utils import info_embed
from cogs.menu import MenuView

# --- ログ設定 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('winglish')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class WinglishBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        await init_db()
        logger.info("✅ データベース初期化完了")

        cogs = ["cogs.onboarding", "cogs.menu", "cogs.vocab", "cogs.svocm", "cogs.reading", "cogs.admin"]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"✅ Cog 読み込み完了: {cog}")
            except Exception as e:
                logger.error(f"❌ Cog 読み込み失敗: {cog} - {e}")

        self.add_view(MenuView())
        logger.info("✅ 永続 View 登録完了")

    async def on_ready(self) -> None:
        logger.info(f"✅ Logged in as {self.user} ({self.user.id})")

    async def on_error(self, event_method: str, *args: Any, **kwargs: Any) -> None:
        logger.exception(f"⚠️ イベントエラー ({event_method})")

# --- スラッシュコマンド ---
bot = WinglishBot()

@bot.tree.command(name="start", description="Winglishを開始（個人鍵チャンネルにメニューを出します）")
async def start_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send("あなたの個人チャンネルにメニューを送ります。", ephemeral=True)

# --- 実行 ---
if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_BOT_TOKEN":
        logger.critical("❌ DISCORD_TOKEN が .env に設定されていません。")
        sys.exit(1)

    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.critical("❌ Discordトークンが無効です。.env を確認してください。")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("🛑 ユーザーによって中断されました。")
    except Exception as e:
        logger.critical(f"💥 予期しないエラー: {e}", exc_info=True)
        sys.exit(1)