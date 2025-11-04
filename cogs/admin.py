import discord
from discord import app_commands
from discord.ext import commands

from utils import info_embed
from cogs.menu import MenuView  # callback付きメインメニュー

def is_manager():
    """管理用ガード（管理者orManage Channels権限）"""
    def predicate(inter: discord.Interaction):
        perms = inter.user.guild_permissions
        return perms.administrator or perms.manage_channels
    return app_commands.check(lambda i: predicate(i))

class WinglishAdmin(commands.Cog):
    """Winglish 運用・復旧コマンド"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="winglish", description="Winglish の管理/復旧用コマンド")

    @group.command(name="menu", description="このチャンネルに Winglish メニュー（ボタン付き）を再掲します")
    @is_manager()
    async def menu(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(
            embed=info_embed("Winglish へようこそ", "学習を開始しましょう👇"),
            view=MenuView()
        )
        await interaction.followup.send("✅ メニューを再掲しました。", ephemeral=True)

    @group.command(name="attach_menu", description="既存メッセージにメニューの View を付け直します（message_id 指定）")
    @app_commands.describe(message_id="ボタンを付け直したいメッセージID")
    @is_manager()
    async def attach_menu(self, interaction: discord.Interaction, message_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            msg = await interaction.channel.fetch_message(int(message_id))
        except Exception as e:
            await interaction.followup.send(f"❌ 取得失敗: {e}", ephemeral=True)
            return
        try:
            await msg.edit(view=MenuView())
            await interaction.followup.send("✅ View を付け直しました。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 編集失敗: {e}", ephemeral=True)

    @group.command(name="reset", description="このチャンネルの直近の Winglish メッセージを掃除してメニューを再掲します")
    @is_manager()
    async def reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        deleted = 0
        try:
            async for m in interaction.channel.history(limit=50):
                if m.author == self.bot.user:
                    try:
                        await m.delete()
                        deleted += 1
                    except Exception:
                        pass
        except Exception:
            pass
        await interaction.channel.send(
            embed=info_embed("Winglish へようこそ", "学習を開始しましょう👇"),
            view=MenuView()
        )
        await interaction.followup.send(f"🧹 掃除 {deleted}件 → ✅ メニュー再掲", ephemeral=True)

    @group.command(name="ping", description="疎通確認（Botの遅延を表示）")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 {round(self.bot.latency*1000)} ms", ephemeral=True)

    @group.command(name="version", description="Botのバージョン/起動確認")
    async def version(self, interaction: discord.Interaction):
        await interaction.response.send_message("Winglish-bot / admin-cog v1.0", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(WinglishAdmin(bot))
