import discord
from discord.ext import commands
from db import get_pool
from utils import info_embed

class Reading(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component: return
        cid = interaction.data.get("custom_id","")
        if cid in {"reading:toeic","reading:csat","reading:eiken1"}:
            await self.show_stub(interaction, cid.split(":")[1])

    async def show_stub(self, interaction: discord.Interaction, kind: str):
        desc = {
            "toeic":"150–200 words / 4択 ×2",
            "csat":"共通テスト風 300–400 words",
            "eiken1":"450–600 words 高難度"
        }[kind]
        await interaction.response.edit_message(embed=info_embed("長文読解（準備中）", desc + "\n\n※MVP後半で実装（本文→設問→採点）。"), view=None)

async def setup(bot: commands.Bot):
    await bot.add_cog(Reading(bot))
