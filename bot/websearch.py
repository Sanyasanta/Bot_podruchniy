from typing import List, Dict
import httpx


class Tavily:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30)

    async def search(self, query: str, max_results: int = 5) -> List[Dict]:
        url = "https://api.tavily.com/search"
        payload = {"api_key": self.api_key, "query": query, "max_results": max_results}
        r = await self.client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return data.get("results", [])

    async def close(self):
        await self.client.aclose()
