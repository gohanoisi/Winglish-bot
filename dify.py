from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, Optional

import httpx  # ★ 非同期HTTP
import requests

logger = logging.getLogger(__name__)

# ==== ENV ====
DIFY_ENDPOINT_RUN = os.getenv("DIFY_ENDPOINT_RUN", "https://api.dify.ai/v1/workflows/run  ")

# 別アプリ（App）で運用している想定：Question用とAnswer用でキーを分離
DIFY_API_KEY_QUESTION = os.getenv("DIFY_API_KEY_QUESTION")  # app-xxxxxxxx (Winglish_reading_Question)
DIFY_API_KEY_ANSWER = os.getenv("DIFY_API_KEY_ANSWER")      # app-yyyyyyyy (Winglish_reading_Answer)

DEFAULT_TIMEOUT_SEC = 60


# ===== Exceptions =====
class DifyError(RuntimeError):
    pass


# ===== Utilities =====
def _clean_fenced_json(text: str) -> str:
    """
    ```json\n{ ... }\n``` のようなフェンス付きテキストを純JSON文字列にする。
    """
    s = text.strip()
    if s.startswith("```"):
        # 先頭の ```json or ``` を除去
        s = s.lstrip("`")
        # 1行目(例えば "json") を落として本文へ
        if "\n" in s:
            s = s.split("\n", 1)[1]
        # 末尾の ``` を除去（残っていれば）
        s = s.rstrip("`").rstrip()
        if s.endswith("```"):
            s = s[:-3].rstrip()
    return s


def _extract_outputs_text(resp_json: Dict[str, Any]) -> Optional[str]:
    """
    Difyのレスポンスから text を抽出する。
    返り値が None の場合は text が見つかっていない。
    """
    # パターン1: {"data":{"outputs":{"text":"...}}}
    try:
        text = resp_json["data"]["outputs"]["text"]
        if isinstance(text, str):
            return text
    except Exception:
        pass

    # パターン2: {"outputs":{"text":"...}}
    try:
        text = resp_json["outputs"]["text"]
        if isinstance(text, str):
            return text
    except Exception:
        pass

    # パターン3: {"text":"..."}（まれ）
    try:
        text = resp_json["text"]
        if isinstance(text, str):
            return text
    except Exception:
        pass

    return None


def _post_workflow(
    inputs: Dict[str, Any],
    user_id: str | int,
    api_key: str,
    endpoint: str = DIFY_ENDPOINT_RUN,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    """
    Dify /workflows/run を叩く共通関数。
    - inputs: Workflowに渡す "inputs" の中身（dict）
    - user_id: 任意のユーザー識別（stringでもintでもOK）
    - api_key: "app-..." で始まる Dify アプリキー
    戻り値: outputs.text（文字列）を返す。存在しなければ DifyError。
    """
    if not api_key:
        raise DifyError("Missing Dify API key for this workflow. Check .env (DIFY_API_KEY_QUESTION / DIFY_API_KEY_ANSWER).")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "inputs": inputs,
        "response_mode": "blocking",
        "user": str(user_id),
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=body, timeout=timeout_sec)
    except requests.RequestException as e:
        raise DifyError(f"Failed to call Dify endpoint: {e}") from e

    if not (200 <= resp.status_code < 300):
        # 可能ならエラーボディを載せる
        detail = None
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        raise DifyError(f"Dify returned HTTP {resp.status_code}: {detail}")

    try:
        resp_json = resp.json()
    except ValueError as e:
        raise DifyError(f"Dify response is not JSON: {resp.text[:500]!r}") from e

    text = _extract_outputs_text(resp_json)
    if text is None:
        raise DifyError(f"Dify response missing outputs.text. Raw: {json.dumps(resp_json)[:800]}")

    return text


# ---------- ★ 非同期ポスト ----------
async def _apost_workflow(
    inputs: Dict[str, Any],
    user_id: str | int,
    api_key: str,
    endpoint: str = DIFY_ENDPOINT_RUN,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    if not api_key:
        raise DifyError("Missing Dify API key. Set DIFY_API_KEY_QUESTION / DIFY_API_KEY_ANSWER")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"inputs": inputs, "response_mode": "blocking", "user": str(user_id)}

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.post(endpoint, headers=headers, json=body)
    if not (200 <= resp.status_code < 300):
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        raise DifyError(f"Dify returned HTTP {resp.status_code}: {detail}")

    try:
        resp_json = resp.json()
    except ValueError as e:
        raise DifyError(f"Dify response is not JSON: {resp.text[:500]!r}") from e

    text = _extract_outputs_text(resp_json)
    if text is None:
        raise DifyError(f"Dify response missing outputs.text. Raw: {json.dumps(resp_json)[:800]}")
    return text


# ===== Public APIs (Reading) =====
def run_reading_question(
    *,
    user_id: int | str,
    training_type: str = "reading",
    current_score: int | float = 50,
    recent_svocm_mistakes: str = "",
    word: str = "",
) -> Dict[str, Any]:
    """
    Winglish_reading_Question を実行し、JSONをdictで返す。
    - Dify側のSYSTEMは、passage/choices/answers を JSON文字列として outputs.text に返す想定。
    """
    inputs = {
        "user_id": str(user_id),
        "training_type": training_type,
        "current_score": current_score,
        "recent_svocm_mistakes": recent_svocm_mistakes,  # JSON文字列でOK（空でも可）
        "word": word,
    }

    raw_text = _post_workflow(inputs, user_id, api_key=DIFY_API_KEY_QUESTION)
    cleaned = _clean_fenced_json(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Question JSON parse failed. Returning raw text for debugging.")
        # 解析エラー時は最低限の形に包んで返す（上位で扱えるように）
        return {"raw_text": raw_text}


def run_reading_answer(
    *,
    user_id: int | str,
    passage: str,
    q1_text: str,
    q1_choices_str: str,  # "A. ... B. ... C. ... D. ..." の1本化文字列（Bubble互換）
    q1_answer: str,       # "A" ~ "D"
    q1_user: str,         # "A" ~ "D"
    q2_text: str,
    q2_choices_str: str,  # 同上
    q2_answer: str,       # "A" ~ "D"
    q2_user: str,         # "A" ~ "D"
) -> Dict[str, Any]:
    """
    Winglish_reading_Answer を実行し、```json フェンス有無に関わらず dict を返す。
    DifyのSYSTEMに合わせて Bubble時代のキー名で inputs を渡す。
    """
    inputs = {
        "user_id": str(user_id),
        "Question": passage,                 # Bubble準拠の大文字Q
        "question_1_text": q1_text,
        "question_1_choice": q1_choices_str,
        "question_1_Answer": q1_answer,
        "question_1_User_Answer": q1_user,
        "question_2_text": q2_text,
        "question_2_choice": q2_choices_str,
        "question_2_Answer": q2_answer,
        "question_2_User_Answer": q2_user,
    }

    raw_text = _post_workflow(inputs, user_id, api_key=DIFY_API_KEY_ANSWER)
    cleaned = _clean_fenced_json(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Answer JSON parse failed. Returning raw text for debugging.")
        return {"raw_text": raw_text}


# ---------- ★ 読解: 非同期API ----------
async def run_reading_question_async(
    *,
    user_id: int | str,
    training_type: str = "reading",
    current_score: int | float = 50,
    recent_svocm_mistakes: str = "",
    word: str = "",
) -> Dict[str, Any]:
    inputs = {
        "user_id": str(user_id),  # ← string必須
        "training_type": training_type,
        "current_score": current_score,
        "recent_svocm_mistakes": recent_svocm_mistakes or "",
        "word": word or "",
    }
    raw_text = await _apost_workflow(inputs, user_id, api_key=DIFY_API_KEY_QUESTION)
    cleaned = _clean_fenced_json(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Question JSON parse failed. Returning raw text")
        return {"raw_text": raw_text}


async def run_reading_answer_async(
    *,
    user_id: int | str,
    passage: str,
    q1_text: str,
    q1_choices_str: str,
    q1_answer: str,
    q1_user: str,
    q2_text: str,
    q2_choices_str: str,
    q2_answer: str,
    q2_user: str,
) -> Dict[str, Any]:
    inputs = {
        "user_id": str(user_id),  # ← string必須
        "Question": passage,
        "question_1_text": q1_text,
        "question_1_choice": q1_choices_str,
        "question_1_Answer": q1_answer,
        "question_1_User_Answer": q1_user,
        "question_2_text": q2_text,
        "question_2_choice": q2_choices_str,
        "question_2_Answer": q2_answer,
        "question_2_User_Answer": q2_user,
    }
    raw_text = await _apost_workflow(inputs, user_id, api_key=DIFY_API_KEY_ANSWER)
    cleaned = _clean_fenced_json(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Answer JSON parse failed. Returning raw text")
        return {"raw_text": raw_text}


# ===== Optional: Health check (起動時ログ用) =====
def health_check() -> Dict[str, Any]:
    """
    起動時に config が揃っているか軽く検査するための関数。
    main.py から呼んでログに出すとトラブルシュートが楽。
    """
    return {
        "endpoint": DIFY_ENDPOINT_RUN,
        "question_key_present": bool(DIFY_API_KEY_QUESTION),
        "answer_key_present": bool(DIFY_API_KEY_ANSWER),
    }