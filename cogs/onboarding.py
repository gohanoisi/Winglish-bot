import discord
from discord.ext import commands
from db import get_pool
from utils import main_menu_view, info_embed

GUILD_CATEGORY_NAME = "Winglish｜個人学習"

class Onboarding(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # 参加時に個人鍵チャンネル作成（存在チェック）
        await self.ensure_private_channel(member)

    async def ensure_private_channel(self, member: discord.Member):
        guild = member.guild
        category = discord.utils.get(guild.categories, name=GUILD_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(GUILD_CATEGORY_NAME)

        # 既存チェック
        ch_name = f"winglish-{member.name}".lower()
        exist = discord.utils.get(category.channels, name=ch_name)
        if exist:
            return exist

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        ch = await guild.create_text_channel(ch_name, category=category, overwrites=overwrites)

        # DBユーザー登録
        pool = await get_pool()
        async with pool.acquire() as con:
            await con.execute("INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING", str(member.id))

        # メインBAM送付（常に最新1つ方針の起点）
        await ch.send(embed=info_embed("Winglish へようこそ", "学習を開始しましょう👇"), view=main_menu_view())
        return ch

async def setup(bot: commands.Bot):
    await bot.add_cog(Onboarding(bot))
