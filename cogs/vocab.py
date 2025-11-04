import discord, random, uuid
from discord.ext import commands
from db import get_pool
from srs import update_srs

async def safe_edit(interaction: discord.Interaction, **kwargs):
    """このインタラクションのメッセージを安全に編集する"""
    try:
        if not interaction.response.is_done():
            # まだレスポンスしていない場合は edit_message でOK
            await interaction.response.edit_message(**kwargs)
            return
    except Exception:
        pass
    # すでにレスポンス済みの場合
    try:
        await interaction.edit_original_response(**kwargs)
    except Exception:
        # それもダメなら元メッセージを直接編集
        await interaction.message.edit(**kwargs)

# 10問提示ビュー（1問ごとにEmbed更新）
class VocabSessionView(discord.ui.View):
    def __init__(self, batch_id, items):
        super().__init__(timeout=180)
        self.batch_id = batch_id
        self.items = items
        self.index = 0

    async def send_current(self, interaction: discord.Interaction):
        if self.index >= len(self.items):
            # 結果
            await safe_edit(interaction,
                            embed=discord.Embed(title="完了", description="10問が終了しました。メインメニューへ戻れます。"),
                            view=None)
            return

        w = self.items[self.index]
        desc = f"**📘 {w['word']}**\n意味：`||{w['jp']}||`\n品詞：{w.get('pos','-')}\n例：`||{(w.get('example') or '-') }||`"
        e = discord.Embed(title=f"Q{self.index+1}/10", description=desc)
        v = discord.ui.View(timeout=180)
        v.add_item(discord.ui.Button(label="覚えた(◎)", style=discord.ButtonStyle.success, custom_id=f"vocab:known:{w['word_id']}"))
        v.add_item(discord.ui.Button(label="忘れそう(△)", style=discord.ButtonStyle.secondary, custom_id=f"vocab:unsure:{w['word_id']}"))
        v.add_item(discord.ui.Button(label="▶ 次へ", style=discord.ButtonStyle.primary, custom_id=f"vocab:next"))
        await safe_edit(interaction, embed=e, view=v)

class Vocab(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component: return
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

    async def start_ten(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # まず defer（この後は edit_original_response で編集する）
        await interaction.response.defer(thinking=False)
        pool = await get_pool()
        async with pool.acquire() as con:
            # SRS/正答率/新規率を考慮して10語抽出（簡易：ランダム＋未学習優先）
            words = await con.fetch("SELECT word_id, word, jp, pos FROM words ORDER BY random() LIMIT 20")
        items = [dict(r) for r in words][:10]
        batch_id = str(uuid.uuid4())

        # セッション保存
        view = VocabSessionView(batch_id, items)
        # ここでは「英単語 10問」に一旦置き換え（optional）
        await interaction.edit_original_response(embed=discord.Embed(title="英単語 10問"), view=None)
        await view.send_current(interaction)

        # バッチ登録
        async with (await get_pool()).acquire() as con:
            await con.execute(
                "INSERT INTO session_batches(user_id, module, batch_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                user_id, "vocab", batch_id
            )

        # メッセージにViewを保持するため、stateに残す（簡易：botインスタンス属性）
        self.bot._vocab_session = view

    async def handle_answer(self, interaction: discord.Interaction, cid: str):
        user_id = str(interaction.user.id)
        quality = 5 if "known" in cid else 2
        word_id = int(cid.split(":")[-1])
        await interaction.response.defer(thinking=False)

        # SRS更新
        pool = await get_pool()
        async with pool.acquire() as con:
            row = await con.fetchrow("SELECT easiness, interval_days, consecutive_correct FROM srs_state WHERE user_id=$1 AND word_id=$2", user_id, word_id)
            if row:
                e,i,c = row["easiness"], row["interval_days"], row["consecutive_correct"]
            else:
                e,i,c = 2.5, 0, 0
            e,i,c,next_review = update_srs(e,i,c, quality)

            await con.execute("""
                INSERT INTO srs_state(user_id, word_id, easiness, interval_days, consecutive_correct, next_review, last_result)
                VALUES($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (user_id, word_id) DO UPDATE
                SET easiness=$3, interval_days=$4, consecutive_correct=$5, next_review=$6, last_result=$7
            """, user_id, word_id, e, i, c, next_review, quality)

            # ログ
            await con.execute("""
                INSERT INTO study_logs(user_id, module, item_id, result)
                VALUES($1,'vocab',$2, $3::jsonb)
            """, user_id, word_id, {"known": quality==5})

        await self.next_item(interaction)

    async def next_item(self, interaction: discord.Interaction):
        view = getattr(self.bot, "_vocab_session", None)
        if not view:
            await interaction.followup.send("セッションが見つかりません。もう一度メニューから開始してください。", ephemeral=True)
            return
        view.index += 1
        await view.send_current(interaction)

    async def prevprev_test(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        await interaction.response.defer(thinking=False)
        pool = await get_pool()
        async with pool.acquire() as con:
            # 2つ前のbatch_idを取得
            rows = await con.fetch("""
                SELECT batch_id FROM session_batches
                WHERE user_id=$1 AND module='vocab'
                ORDER BY created_at DESC LIMIT 3
            """, user_id)
        if len(rows) < 3:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="前々回テスト",
                    description=f"batch: {target}\n※4択テストは今後実装（MVP後半）"
                ),
                view=None
            )
            return
        target = rows[2]["batch_id"]
        await interaction.edit_original_response(
            embed=discord.Embed(
                title="前々回テスト",
                description=f"batch: {target}\n※4択テストは今後実装（MVP後半）"
            ),
            view=None
        )

    async def weak_test(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        await interaction.response.defer(thinking=False)
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
            await interaction.edit_original_response(
                embed=discord.Embed(title="苦手テスト", description="対象がありません。"),
                view=None
            )
            return
        # ここでは簡易表示
        words = "\n".join([f"- **{r['word']}** (`||{r['jp']}||`)" for r in rows])
        await interaction.edit_original_response(
            embed=discord.Embed(title="苦手テスト（候補）", description=words),
            view=None
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Vocab(bot))
