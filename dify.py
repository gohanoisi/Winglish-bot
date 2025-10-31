import httpx
from config import DIFY_API_KEY, DIFY_ENDPOINT_RUN, DIFY_ENDPOINT_CHAT

HEADERS = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}

async def run_workflow(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(DIFY_ENDPOINT_RUN, headers=HEADERS, json=payload)
        r.raise_for_status()
        return r.json()

async def chat_messages(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(DIFY_ENDPOINT_CHAT, headers=HEADERS, json=payload)
        r.raise_for_status()
        return r.json()
