import discord, random, uuid
from discord.ext import commands
from db import get_pool
from srs import update_srs

# ------------------------
# 共通ユーティリティ
# ------------------------
async def ensure_defer(interaction: discord.Interaction):
    """未応答ならdeferする（二重deferを回避）"""
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=False)
    except Exception:
        pass

async def safe_edit(interaction: discord.Interaction, **kwargs):
    """このインタラクションのメッセージを安全に編集する"""
    try:
        if not interaction.response.is_done():
            await interaction.response.edit_message(**kwargs)
            return
    except Exception:
        pass
    try:
        await interaction.edit_original_response(**kwargs)
    except Exception:
        # それもダメなら元メッセージを直接編集
        try:
            await interaction.message.edit(**kwargs)
        except Exception:
            pass

# ------------------------
# 完了後や中断時に表示するメニュー View
# ------------------------
class VocabMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="英単語 10問", style=discord.ButtonStyle.primary, custom_id="vocab:ten")
    async def ten_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # on_interaction側が拾うのでここでは何もしない
        pass

    @discord.ui.button(label="前々回テスト", style=discord.ButtonStyle.secondary, custom_id="vocab:prevprev")
    async def prevprev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="苦手テスト", style=discord.ButtonStyle.secondary, custom_id="vocab:weak")
    async def weak_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="戻る", style=discord.ButtonStyle.danger)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        e = discord.Embed(title="Winglish — 英単語", description="学習メニューを選んでください。")
        await safe_edit(interaction, embed=e, view=VocabMenuView())

# ------------------------
# 10問提示ビュー（1問ごとにEmbed更新）
# ------------------------
class VocabSessionView(discord.ui.View):
    def __init__(self, batch_id, items):
        super().__init__(timeout=180)
        self.batch_id = batch_id
        self.items = items
        self.index = 0
        self.busy = False  # 多重クリック防止

    async def send_current(self, interaction: discord.Interaction):
        if self.index >= len(self.items):
            await safe_edit(
                interaction,
                embed=discord.Embed(title="完了", description="10問が終了しました。メインメニューへ戻れます。"),
                view=VocabMenuView()
            )
            return

        w = self.items[self.index]
        jp = w.get('jp','-')
        pos = w.get('pos','-')
        ex_en = w.get('example_en') or '-'
        ex_ja = w.get('example_ja') or '-'
        syns = ", ".join(w.get('synonyms',[]) or []) or '—'
        drv  = ", ".join(w.get('derived',[])  or []) or '—'

        desc = (
            f"**📘 {w['word']}**\n"
            f"意味：||{jp}||\n"
            f"品詞：{pos}\n"
            f"例文：{ex_en}\n"
            f"日本語訳：||{ex_ja}||\n"
            f"類義語：{syns} / 派生語：{drv}"
        )
        e = discord.Embed(title=f"Q{self.index+1}/10", description=desc)
        v = discord.ui.View(timeout=180)
        v.add_item(discord.ui.Button(label="覚えた(◎)", style=discord.ButtonStyle.success, custom_id=f"vocab:known:{w['word_id']}"))
        v.add_item(discord.ui.Button(label="忘れそう(△)", style=discord.ButtonStyle.secondary, custom_id=f"vocab:unsure:{w['word_id']}"))
        v.add_item(discord.ui.Button(label="▶ 次へ", style=discord.ButtonStyle.primary, custom_id="vocab:next"))
        await safe_edit(interaction, embed=e, view=v)

# ------------------------
# Cog本体
# ------------------------
class Vocab(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    # 直近メッセージのボタンを無効化（見た目で連打抑止）
    async def _disable_current_buttons(self, interaction: discord.Interaction):
        try:
            new_view = discord.ui.View(timeout=0)
            for row in interaction.message.components:
                # Rowの再構築
                for comp in getattr(row, "children", []):
                    if isinstance(comp, discord.ui.Button):
                        b = discord.ui.Button(
                            label=comp.label, 
                            style=comp.style, 
                            custom_id=comp.custom_id, 
                            url=comp.url if hasattr(comp, "url") else None,
                            disabled=True
                        )
                        new_view.add_item(b)
            await safe_edit(interaction, view=new_view)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        cid = interaction.data.get("custom_id","")

        if cid == "vocab:ten":
            await self.start_ten(interaction)

        elif cid.startswith("vocab:known:") or cid.startswith("vocab:unsure:"):
            await self.handle_answer(interaction, cid)

        elif cid == "vocab:next":
            await self.next_item(interaction)

        elif cid == "vocab:prevprev":
            await self.prevprev_test(interaction)

        elif cid == "vocab:weak":
            await self.weak_test(interaction)

    # 10問スタート
    async def start_ten(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        await ensure_defer(interaction)

        pool = await get_pool()
        async with pool.acquire() as con:
            words = await con.fetch("""
                SELECT word_id, word, jp, pos, example_en, example_ja, synonyms, derived
                FROM words
                ORDER BY random()
                LIMIT 20
            """)
        items = [dict(r) for r in words][:10]
        batch_id = str(uuid.uuid4())

        view = VocabSessionView(batch_id, items)
        await safe_edit(interaction, embed=discord.Embed(title="英単語 10問"), view=None)
        await view.send_current(interaction)

        async with (await get_pool()).acquire() as con:
            await con.execute(
                "INSERT INTO session_batches(user_id, module, batch_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                user_id, "vocab", batch_id
            )

        self.bot._vocab_session = view

    # 解答処理（覚えた/忘れそう）
    async def handle_answer(self, interaction: discord.Interaction, cid: str):
        await ensure_defer(interaction)

        # セッション取得＆多重実行ガード
        view = getattr(self.bot, "_vocab_session", None)
        if isinstance(view, VocabSessionView):
            if view.busy:
                return
            view.busy = True
        try:
            await self._disable_current_buttons(interaction)

            user_id = str(interaction.user.id)
            quality = 5 if "known" in cid else 2
            word_id = int(cid.split(":")[-1])

            pool = await get_pool()
            async with pool.acquire() as con:
                row = await con.fetchrow(
                    "SELECT easiness, interval_days, consecutive_correct FROM srs_state WHERE user_id=$1 AND word_id=$2",
                    user_id, word_id
                )
                if row:
                    e, i, c = row["easiness"], row["interval_days"], row["consecutive_correct"]
                else:
                    e, i, c = 2.5, 0, 0

                e, i, c, next_review = update_srs(e, i, c, quality)
                await con.execute("""
                    INSERT INTO srs_state(user_id, word_id, easiness, interval_days, consecutive_correct, next_review)
                    VALUES($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (user_id, word_id) DO UPDATE
                    SET easiness=$3, interval_days=$4, consecutive_correct=$5, next_review=$6
                """, user_id, word_id, e, i, c, next_review)

            # 次へ
            if isinstance(view, VocabSessionView):
                view.index += 1
                await view.send_current(interaction)
            else:
                await self.start_ten(interaction)
        finally:
            if isinstance(view, VocabSessionView):
                view.busy = False

    # 明示的な「次へ」
    async def next_item(self, interaction: discord.Interaction):
        await ensure_defer(interaction)
        view = getattr(self.bot, "_vocab_session", None)
        if isinstance(view, VocabSessionView):
            if view.busy:
                return
            view.busy = True
            try:
                await self._disable_current_buttons(interaction)
                view.index += 1
                await view.send_current(interaction)
            finally:
                view.busy = False
        else:
            await self.start_ten(interaction)

    # 前々回テスト（プレースホルダ）
    async def prevprev_test(self, interaction: discord.Interaction):
        await ensure_defer(interaction)
        user_id = str(interaction.user.id)
        pool = await get_pool()
        async with pool.acquire() as con:
            rows = await con.fetch("""
                SELECT batch_id FROM session_batches
                WHERE user_id=$1 AND module='vocab'
                ORDER BY created_at DESC LIMIT 3
            """, user_id)

        if len(rows) < 3:
            e = discord.Embed(title="前々回テスト", description="履歴が足りません。")
            await safe_edit(interaction, embed=e, view=VocabMenuView())
            return

        target = rows[2]["batch_id"]
        e = discord.Embed(
            title="前々回テスト",
            description=f"batch: {target}\n※4択テストは今後実装（MVP後半）"
        )
        await safe_edit(interaction, embed=e, view=VocabMenuView())

    # 苦手テスト（候補表示）
    async def weak_test(self, interaction: discord.Interaction):
        await ensure_defer(interaction)
        user_id = str(interaction.user.id)
        pool = await get_pool()
        async with pool.acquire() as con:
            rows = await con.fetch("""
                SELECT s.word_id, w.word, w.jp, w.pos
                FROM srs_state s
                JOIN words w ON w.word_id=s.word_id
                WHERE s.user_id=$1 AND (s.next_review <= CURRENT_DATE OR s.consecutive_correct < 2)
                ORDER BY s.consecutive_correct ASC NULLS FIRST, s.next_review ASC NULLS LAST
                LIMIT 10
            """, user_id)

        if not rows:
            await safe_edit(interaction,
                            embed=discord.Embed(title="苦手テスト", description="対象がありません。"),
                            view=VocabMenuView())
            return

        words = "\n".join([f"- **{r['word']}**（意味：||{r['jp']}||）" for r in rows])
        await safe_edit(interaction,
                        embed=discord.Embed(title="苦手テスト（候補）", description=words),
                        view=VocabMenuView())

async def setup(bot: commands.Bot):
    await bot.add_cog(Vocab(bot))
