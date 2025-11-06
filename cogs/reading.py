from dify import run_reading_question_async, run_reading_answer_async
import discord
from discord.ext import commands

class ReadingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._live_views = set()   # ★ 参照保持

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

        # 解説
        emb_r = discord.Embed(title="🧠 解説 / フィードバック")
        qs = result.get("questions", [])
        if len(qs) >= 1:
            emb_r.add_field(name="Q1 Reason", value=qs[0].get("q1_reason", "-"), inline=False)
            emb_r.add_field(name="Q1 Feedback", value=qs[0].get("feedback", "-"), inline=False)
        if len(qs) >= 2:
            emb_r.add_field(name="Q2 Reason", value=qs[1].get("q2_reason", "-"), inline=False)
            emb_r.add_field(name="Q2 Feedback", value=qs[1].get("feedback", "-"), inline=False)
        emb_r.add_field(name="Overall", value=result.get("overall_feedback", "-"), inline=False)
        await ctx.send(embed=emb_r)


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
        self.session[f"q{self.number}_user"] = key
        await interaction.response.defer()
        await interaction.message.edit(view=None)  # ボタン無効化
        await self.on_done(self.session, self.number)

    async def on_timeout(self):
        # 将来的にメッセージに「タイムアウト」を出すならここで
        return

async def setup(bot):
    await bot.add_cog(ReadingCog(bot))
