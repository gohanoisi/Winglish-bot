import discord, random, uuid
from discord.ext import commands
from db import get_pool
from srs import update_srs
from asyncpg.types import Json

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
# （※ menu.py にも VocabMenuView があるが、ここは完了画面用の最小構成で自給自足）
# ------------------------
class VocabMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="英単語 10問", style=discord.ButtonStyle.primary, custom_id="vocab:ten")
    async def ten_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # on_interaction 側で拾う

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
    def __init__(self, batch_id, items, title_prefix: str = "英単語"):
        super().__init__(timeout=180)
        self.batch_id = batch_id
        self.items = items
        self.index = 0
        self.busy = False  # 多重クリック防止
        self.title_prefix = title_prefix  # 「英単語」「前々回」「苦手」など

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
        e = discord.Embed(title=f"{self.title_prefix} Q{self.index+1}/10", description=desc)
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
                for comp in getattr(row, "children", []):
                    if isinstance(comp, discord.ui.Button):
                        b = discord.ui.Button(
                            label=comp.label, 
                            style=comp.style, 
                            custom_id=comp.custom_id, 
                            url=getattr(comp, "url", None),
                            disabled=True
                        )
                        new_view.add_item(b)
            await safe_edit(interaction, view=new_view)
        except Exception:
            pass

    # 共通: DBレコード → items 辞書配列
    def _rows_to_items(self, rows):
        items = []
        for r in rows:
            items.append({
                "word_id": r["word_id"],
                "word": r["word"],
                "jp": r.get("jp"),
                "pos": r.get("pos"),
                "example_en": r.get("example_en"),
                "example_ja": r.get("example_ja"),
                "synonyms": r.get("synonyms"),
                "derived": r.get("derived"),
            })
        return items

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

    # 10問スタート（通常）
    async def start_ten(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        await ensure_defer(interaction)

        pool = await get_pool()
        async with pool.acquire() as con:
            rows = await con.fetch("""
                SELECT word_id, word, jp, pos, example_en, example_ja, synonyms, derived
                FROM words
                ORDER BY random()
                LIMIT 20
            """)
        items = self._rows_to_items(rows)[:10]
        random.shuffle(items)  # 念のためシャッフル
        batch_id = str(uuid.uuid4())

        # セッション保存
        view = VocabSessionView(batch_id, items, title_prefix="英単語")
        await safe_edit(interaction, embed=discord.Embed(title="英単語 10問を開始します"), view=None)
        await view.send_current(interaction)

        # バッチ登録 + 出題ログ（item_idだけ先に紐づけ。回答時に result を追記する運用でもOK）
        pool = await get_pool()
        async with pool.acquire() as con:
            await con.execute(
                "INSERT INTO session_batches(user_id, module, batch_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                user_id, "vocab", batch_id
            )
            # ここで問一覧をログに置いておくと「前々回テスト」で再取得できる
            for it in items:
                await con.execute("""
                    INSERT INTO study_logs(user_id, module, item_id, batch_id, result)
                    VALUES($1,'vocab',$2,$3,$4::jsonb)
                """, user_id, it["word_id"], batch_id, None)

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
                    INSERT INTO srs_state(user_id, word_id, easiness, interval_days, consecutive_correct, next_review, last_result)
                    VALUES($1,$2,$3,$4,$5,$6,$7)
                    ON CONFLICT (user_id, word_id) DO UPDATE
                    SET easiness=$3, interval_days=$4, consecutive_correct=$5, next_review=$6, last_result=$7
                """, user_id, word_id, e, i, c, next_review, quality)

                # 任意：回答ログ更新（最後の結果だけ簡易に残す）
                await con.execute("""
                    INSERT INTO study_logs(user_id, module, item_id, batch_id, result)
                    VALUES($1,'vocab',$2,$3,$4::jsonb)
                """, user_id, word_id, getattr(view, "batch_id", None), Json({"quality": quality}))

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

    # 前々回テスト → 前々回の batch の item_id を study_logs から復元し、同UIで10問出題
    async def prevprev_test(self, interaction: discord.Interaction):
        await ensure_defer(interaction)
        user_id = str(interaction.user.id)
        pool = await get_pool()
        async with pool.acquire() as con:
            rows = await con.fetch("""
                SELECT batch_id FROM session_batches
                WHERE user_id=$1 AND module='vocab'
                ORDER BY created_at DESC
                LIMIT 3
            """, user_id)

        if len(rows) < 3:
            e = discord.Embed(title="前々回テスト", description="履歴が足りません。")
            await safe_edit(interaction, embed=e, view=VocabMenuView())
            return

        target_batch = rows[2]["batch_id"]

        # そのバッチの item_id を復元
        pool = await get_pool()
        async with pool.acquire() as con:
            item_ids = await con.fetch("""
                SELECT item_id FROM study_logs
                WHERE user_id=$1 AND module='vocab' AND batch_id=$2 AND item_id IS NOT NULL
            """, user_id, target_batch)
            item_ids = [r["item_id"] for r in item_ids][:10]

            if not item_ids:
                await safe_edit(interaction,
                                embed=discord.Embed(title="前々回テスト", description="対象の出題履歴が見つかりませんでした。"),
                                view=VocabMenuView())
                return

            # その item_id で words を取得（順序はシャッフル）
            rows = await con.fetch(f"""
                SELECT word_id, word, jp, pos, example_en, example_ja, synonyms, derived
                FROM words
                WHERE word_id = ANY($1::int[])
            """, item_ids)

        items = self._rows_to_items(rows)
        random.shuffle(items)
        batch_id = str(uuid.uuid4())
        view = VocabSessionView(batch_id, items, title_prefix="前々回")

        await safe_edit(interaction, embed=discord.Embed(title="前々回 10問を開始します"), view=None)
        await view.send_current(interaction)

        # 新しいバッチとして登録（再テストもログに残す）
        pool = await get_pool()
        async with pool.acquire() as con:
            await con.execute(
                "INSERT INTO session_batches(user_id, module, batch_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                user_id, "vocab", batch_id
            )
            for it in items:
                await con.execute("""
                    INSERT INTO study_logs(user_id, module, item_id, batch_id, result)
                    VALUES($1,'vocab',$2,$3,$4::jsonb)
                """, user_id, it["word_id"], batch_id, Json({"source": "prevprev"}))

        self.bot._vocab_session = view

    # 苦手テスト → SRSからランダム抽出し、同UIで10問出題
    async def weak_test(self, interaction: discord.Interaction):
        await ensure_defer(interaction)
        user_id = str(interaction.user.id)
        pool = await get_pool()
        async with pool.acquire() as con:
            rows = await con.fetch("""
                SELECT w.word_id, w.word, w.jp, w.pos, w.example_en, w.example_ja, w.synonyms, w.derived
                FROM srs_state s
                JOIN words w ON w.word_id=s.word_id
                WHERE s.user_id=$1
                  AND (s.next_review <= CURRENT_DATE OR s.consecutive_correct < 2 OR s.last_result < 3)
                ORDER BY random()
                LIMIT 20
            """, user_id)

        if not rows:
            await safe_edit(interaction,
                            embed=discord.Embed(title="苦手テスト", description="対象がありません。"),
                            view=VocabMenuView())
            return

        items = self._rows_to_items(rows)[:10]
        random.shuffle(items)
        batch_id = str(uuid.uuid4())
        view = VocabSessionView(batch_id, items, title_prefix="苦手")

        await safe_edit(interaction, embed=discord.Embed(title="苦手 10問を開始します"), view=None)
        await view.send_current(interaction)

        # バッチ登録 + ログ
        pool = await get_pool()
        async with pool.acquire() as con:
            await con.execute(
                "INSERT INTO session_batches(user_id, module, batch_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                user_id, "vocab", batch_id
            )
            for it in items:
                await con.execute("""
                    INSERT INTO study_logs(user_id, module, item_id, batch_id, result)
                    VALUES($1,'vocab',$2,$3,$4::jsonb)
                """, user_id, it["word_id"], batch_id, Json({"source": "weak"}))

        self.bot._vocab_session = view

async def setup(bot: commands.Bot):
    await bot.add_cog(Vocab(bot))
