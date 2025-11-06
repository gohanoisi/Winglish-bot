from dify import run_reading_question_async, run_reading_answer_async
import discord
from discord.ext import commands

class ReadingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._live_views = set()   # ★ 参照保持

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        cid = interaction.data.get("custom_id", "")

        # 共有: 直前メッセージのボタンを無効化するユーティリティ
        async def _disable_buttons_only(msg: discord.Message):
            try:
                disabled = discord.ui.View(timeout=0)
                for row in msg.components:
                    for comp in getattr(row, "children", []):
                        if isinstance(comp, discord.ui.Button):
                            b = discord.ui.Button(
                                label=comp.label, style=comp.style,
                                custom_id=comp.custom_id, url=getattr(comp, "url", None),
                                disabled=True
                            )
                            disabled.add_item(b)
                await msg.edit(view=disabled)  # ★ Embedは触らない
            except Exception:
                pass

        if cid == "reading:again":
            # 解説メッセージはそのまま残す → ボタンだけ無効化
            await _disable_buttons_only(interaction.message)

            # 新規メッセージとして「生成中…」を出し、そこから再出題
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(title="長文読解", description="問題を生成中です…（数十秒かかることがあります）"),
                    view=None
                )
            except discord.InteractionResponded:
                await interaction.followup.send(
                    embed=discord.Embed(title="長文読解", description="問題を生成中です…（数十秒かかることがあります）"),
                    wait=True
                )

            # 新しく出したメッセージから ctx を作って再出題
            # （直前sendのメッセージは followup の戻り値を拾えないため、チャンネルからctxでOK）
            ctx = await interaction.client.get_context(interaction.message)
            await self.start_reading(ctx, kind="toeic")

        elif cid == "reading:back_main":
            # 解説メッセージはそのまま残す → ボタンだけ無効化
            await _disable_buttons_only(interaction.message)

            # 新規メッセージとしてメニューを送る
            from utils import info_embed
            from cogs.menu import MenuView
            try:
                await interaction.response.send_message(
                    embed=info_embed("Winglish へようこそ", "学習を開始しましょう👇"),
                    view=MenuView()
                )
            except discord.InteractionResponded:
                await interaction.followup.send(
                    embed=info_embed("Winglish へようこそ", "学習を開始しましょう👇"),
                    view=MenuView(),
                    wait=True
                )

    @commands.command(name="reading")
    async def start_reading(self, ctx, kind: str = "toeic"):
        """例: !reading toeic"""
        async with ctx.channel.typing():  # ← 入力中…を維持
            q = await run_reading_question_async(
                user_id=ctx.author.id,
                training_type="reading",
                current_score=50,
                recent_svocm_mistakes="[]",
                word=""
            )

            passage = q.get("passage", q.get("raw_text", ""))
            q1_text = q.get("question_1_text", "")
            q2_text = q.get("question_2_text", "")
            q1_choices = {
                "A": q.get("question_1_choice_A"),
                "B": q.get("question_1_choice_B"),
                "C": q.get("question_1_choice_C"),
                "D": q.get("question_1_choice_D"),
            }
            q2_choices = {
                "A": q.get("question_2_choice_A"),
                "B": q.get("question_2_choice_B"),
                "C": q.get("question_2_choice_C"),
                "D": q.get("question_2_choice_D"),
            }
            q1_answer = q.get("question_1_answer")
            q2_answer = q.get("question_2_answer")

            # 本文
            emb_p = discord.Embed(title="📖 Reading Passage", description=passage)
            await ctx.send(embed=emb_p)

            # セッション
            session = {
                "passage": passage,
                "q1_text": q1_text, "q1_choices": q1_choices, "q1_answer": q1_answer, "q1_user": None,
                "q2_text": q2_text, "q2_choices": q2_choices, "q2_answer": q2_answer, "q2_user": None,
                "author_id": ctx.author.id,
            }

        # Q1表示（typingの外でOK）
        await self._send_question(ctx, session, number=1)

    async def _send_question(self, ctx, session, number: int):
        q_text = session[f"q{number}_text"]; choices = session[f"q{number}_choices"]
        emb_q = discord.Embed(title=f"Q{number}", description=q_text)

        # 選択肢本文をEmbedに表示
        lines = []
        for k in ("A", "B", "C", "D"):
            v = choices.get(k)
            if v:
                lines.append(f"**{k}.** {v}")
        if lines:
            emb_q.add_field(name="Choices", value="\n".join(lines), inline=False)

        # View作成（A/B/C/Dボタン）＋ 参照保持（GC防止）
        view = ChoiceView(
            session=session,
            number=number,
            on_done=lambda s, n=number: self._on_answer(ctx, s, n),
            timeout=180
        )
        for key in ("A", "B", "C", "D"):
            if choices.get(key):
                view.add_item(ChoiceButton(label=key, custom_id=f"{number}:{key}", key=key))
        self._live_views.add(view)  # ★ 参照保持

        await ctx.send(embed=emb_q, view=view)

    async def _on_answer(self, ctx, session, answered_number: int):
        # Q1の直後→Q2へ、Q2の直後→採点
        if answered_number == 1:
            await self._send_question(ctx, session, number=2)
            return

        # 採点
        def join_choices(d):
            return " ".join([f"{k}. {v}" for k, v in d.items() if v])

        # 入力中…インジケータをONにしてからDifyを叩く
        async with ctx.channel.typing():
            result = await run_reading_answer_async(
                user_id=session["author_id"],
                passage=session["passage"],
                q1_text=session["q1_text"],
                q1_choices_str=join_choices(session["q1_choices"]),
                q1_answer=session["q1_answer"],
                q1_user=session["q1_user"],
                q2_text=session["q2_text"],
                q2_choices_str=join_choices(session["q2_choices"]),
                q2_answer=session["q2_answer"],
                q2_user=session["q2_user"],
            )

        # 解説Embed作成（ユーザーの選択肢も明示）
        emb_r = discord.Embed(title="🌸 解説 / フィードバック")
        qs = result.get("questions", [])
        if len(qs) >= 1:
            emb_r.add_field(name="Q1 Reason", value=qs[0].get("q1_reason", "-"), inline=False)
            emb_r.add_field(name="Q1 Feedback", value=qs[0].get("feedback", "-"), inline=False)
            if session.get("q1_user"):
                emb_r.add_field(name="Q1 Your choice", value=f"**{session['q1_user']}**", inline=True)
                emb_r.add_field(name="Q1 Correct", value=f"**{session['q1_answer']}**", inline=True)
        if len(qs) >= 2:
            emb_r.add_field(name="Q2 Reason", value=qs[1].get("q2_reason", "-"), inline=False)
            emb_r.add_field(name="Q2 Feedback", value=qs[1].get("feedback", "-"), inline=False)
            if session.get("q2_user"):
                emb_r.add_field(name="Q2 Your choice", value=f"**{session['q2_user']}**", inline=True)
                emb_r.add_field(name="Q2 Correct", value=f"**{session['q2_answer']}**", inline=True)
        emb_r.add_field(name="Overall", value=result.get("overall_feedback", "-"), inline=False)
        await ctx.send(embed=emb_r, view=ReadingEndView())


class ChoiceButton(discord.ui.Button):
    def __init__(self, label, custom_id, key):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=custom_id)
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        view: ChoiceView = self.view  # type: ignore
        await view.record_answer(interaction, self.key)


class ChoiceView(discord.ui.View):
    def __init__(self, session, number, on_done, timeout=180):
        super().__init__(timeout=timeout)
        self.session = session
        self.number = number
        self.on_done = on_done

    async def record_answer(self, interaction: discord.Interaction, key: str):
        # ユーザーの選択を保存
        self.session[f"q{self.number}_user"] = key

        # 既存のQカードに「あなたの選択」を追記して示す
        try:
            emb = interaction.message.embeds[0] if interaction.message.embeds else None
            if emb is not None:
                emb = emb.copy()
                # すでにフィールドがあるなら追加、なければ新規
                emb.add_field(name="Your choice", value=f"**{key}**", inline=True)
                await interaction.response.edit_message(embed=emb, view=None)
            else:
                await interaction.response.edit_message(view=None)
        except discord.InteractionResponded:
            try:
                await interaction.message.edit(view=None)
            except Exception:
                pass

        # 次の処理へ（Q1→Q2 or 採点へ）
        await self.on_done(self.session, self.number)

    async def on_timeout(self):
        # 将来的にメッセージに「タイムアウト」を出すならここで
        return

class ReadingEndView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="もう一問", style=discord.ButtonStyle.success, custom_id="reading:again"))
        # ★ 衝突回避のため back は独自IDに
        self.add_item(discord.ui.Button(label="メニューへ戻る", style=discord.ButtonStyle.secondary, custom_id="reading:back_main"))

async def setup(bot):
    await bot.add_cog(ReadingCog(bot))
