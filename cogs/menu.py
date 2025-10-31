import discord
from discord.ext import commands
from utils import info_embed, main_menu_view

class MenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="英単語", style=discord.ButtonStyle.primary, custom_id="menu:vocab")
    async def vocab_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._replace_with_new_bam(interaction, info_embed("英単語", "10問 / 前々回テスト / 苦手テスト / 戻る"), VocabMenuView())

    @discord.ui.button(label="英文解釈", style=discord.ButtonStyle.primary, custom_id="menu:svocm")
    async def svocm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._replace_with_new_bam(interaction, info_embed("英文解釈（SVOCM）", "文型別 or ランダム / モーダル解答"), SvocmMenuView())

    @discord.ui.button(label="長文読解", style=discord.ButtonStyle.primary, custom_id="menu:reading")
    async def reading_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._replace_with_new_bam(interaction, info_embed("長文読解", "TOEIC/共通テスト/英検1級 から選択"), ReadingMenuView())

    async def _replace_with_new_bam(self, interaction, embed, view):
        try:
            await interaction.response.edit_message(embed=embed, view=view)
        except discord.InteractionResponded:
            await interaction.message.edit(embed=embed, view=view)

# サブメニューViews（最低限）
class VocabMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="10問", style=discord.ButtonStyle.success, custom_id="vocab:ten"))
        self.add_item(discord.ui.Button(label="前々回テスト", style=discord.ButtonStyle.secondary, custom_id="vocab:prevprev"))
        self.add_item(discord.ui.Button(label="苦手テスト", style=discord.ButtonStyle.danger, custom_id="vocab:weak"))
        self.add_item(discord.ui.Button(label="戻る", style=discord.ButtonStyle.secondary, custom_id="back:main"))

class SvocmMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i in range(1,6):
            self.add_item(discord.ui.Button(label=f"第{i}文型", custom_id=f"svocm:pattern:{i}"))
        self.add_item(discord.ui.Button(label="ランダム", style=discord.ButtonStyle.success, custom_id="svocm:random"))
        self.add_item(discord.ui.Button(label="戻る", style=discord.ButtonStyle.secondary, custom_id="back:main"))

class ReadingMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for label, cid in [
            ("TOEIC短文", "reading:toeic"),
            ("共通テスト風", "reading:csat"),
            ("英検1級風", "reading:eiken1"),
        ]:
            self.add_item(discord.ui.Button(label=label, custom_id=cid))
        self.add_item(discord.ui.Button(label="戻る", style=discord.ButtonStyle.secondary, custom_id="back:main"))

class Menu(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.type == discord.InteractionType.component: return
        cid = interaction.data.get("custom_id", "")
        if cid == "back:main":
            await interaction.response.edit_message(embed=info_embed("Winglish へようこそ","学習を開始しましょう👇"), view=MenuView())

async def setup(bot: commands.Bot):
    await bot.add_cog(Menu(bot))
