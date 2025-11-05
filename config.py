from dotenv import load_dotenv
import os

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# DATABASE_URL  = os.getenv("DATABASE_URL")
# PUBLIC優先 → なければ従来のDATABASE_URLを見る
DATABASE_URL = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
DIFY_API_KEY  = os.getenv("DIFY_API_KEY")
DIFY_ENDPOINT_RUN  = os.getenv("DIFY_ENDPOINT_RUN", "https://api.dify.ai/v1/workflows/run")
DIFY_ENDPOINT_CHAT = os.getenv("DIFY_ENDPOINT_CHAT", "https://api.dify.ai/v1/chat-messages")
