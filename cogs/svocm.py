import discord
from discord.ext import commands
from db import get_pool
from dify import run_workflow
from utils import info_embed

class SvocmModal(discord.ui.Modal, title="SVOCM 解答"):
    s = discord.ui.TextInput(label="S", required=True)
    v = discord.ui.TextInput(label="V", required=True)
    o1 = discord.ui.TextInput(label="O1", required=False)
    o2 = discord.ui.TextInput(label="O2", required=False)
    c = discord.ui.TextInput(label="C", required=False)
    m = discord.ui.TextInput(label="M", required=False)

    def __init__(self, sentence_en: str, item_id: int):
        super().__init__()
        self.sentence_en = sentence_en
        self.item_id = item_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=False)

        payload = {
            "inputs": {
                "user_id": str(interaction.user.id),
                "Question": self.sentence_en,
                "Answer_S": str(self.s),
                "Answer_V": str(self.v),
                "Answer_O1": str(self.o1),
                "Answer_O2": str(self.o2),
                "Answer_C": str(self.c),
                "Answer_M": str(self.m),
                "question_id": str(self.item_id),
                "training_type": "SVOCM"
            },
            "response_mode": "blocking",
            "user": str(interaction.user.id)
        }
        try:
            res = await run_workflow(payload)
            text = res.get("data", {}).get("outputs", {}).get("text") or str(res)
        except Exception as e:
            text = f"採点APIエラー: {e}"

        # ログ保存
        pool = await get_pool()
        async with pool.acquire() as con:
            await con.execute("""
              INSERT INTO study_logs(user_id, module, item_id, result)
              VALUES($1,'svocm',$2,$3::jsonb)
            """, str(interaction.user.id), int(self.item_id), {"feedback": text})

        await interaction.followup.send(embed=discord.Embed(title="SVOCM 採点", description=text))

class Svocm(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component: return
        cid = interaction.data.get("custom_id","")
        if cid.startswith("svocm:pattern:"):
            pattern = int(cid.split(":")[-1])
            await self.show_item(interaction, pattern=pattern)
        elif cid == "svocm:random":
            await self.show_item(interaction, pattern=None)

    async def show_item(self, interaction: discord.Interaction, pattern: int|None):
        pool = await get_pool()
        async with pool.acquire() as con:
            if pattern:
                row = await con.fetchrow("SELECT * FROM svocm_items WHERE pattern=$1 ORDER BY random() LIMIT 1", pattern)
            else:
                row = await con.fetchrow("SELECT * FROM svocm_items ORDER BY random() LIMIT 1")
        if not row:
            await interaction.response.edit_message(embed=info_embed("英文解釈", "問題がありません（管理者に連絡してください）。"), view=None)
            return

        sentence = row["sentence_en"]
        e = discord.Embed(
            title="SVOCM 問題",
            description=f"{sentence}\n\n（ヒントは ||スポイラー|| で運用可）"  
        )
        view = discord.ui.View()
        modal = SvocmModal(sentence, row["item_id"])
        # モーダル起動ボタン
        async def on_answer(i: discord.Interaction):
            await i.response.send_modal(modal)
        btn = discord.ui.Button(label="解答する", style=discord.ButtonStyle.primary)
        btn.callback = on_answer
        view.add_item(btn)
        await interaction.response.edit_message(embed=e, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Svocm(bot))
