import os
import json
from typing import List, Dict, Optional
import httpx


class CloudflareAI:
    def __init__(self, account_id: str, api_token: str, model: str = "@cf/meta/llama-3.1-8b-instruct"):
        self.account_id = account_id
        self.api_token = api_token
        self.model = model
        self.base = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        self.client = httpx.AsyncClient(timeout=60)

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        payload = {"messages": messages}
        r = await self.client.post(self.base, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        # Workers AI returns result in data["result"]["response"] or similar; handle both common shapes
        result = data.get("result") or {}
        text = result.get("response") or result.get("output_text") or ""
        return text

    async def close(self):
        await self.client.aclose()
