"""
Memory client — talks to the memory-service sidecar (localhost:4011).

Three operations:
  - add_memories(agent_id, messages, user_id=None)  → stores deal transcript
  - search_memories(agent_id, query)                → retrieves relevant context
  - get_memory_hash(agent_id)                       → SHA-256 of all agent memory rows
"""
import os
import httpx

MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL", "http://localhost:4011")


async def add_memories(agent_id: str, messages: list[dict], user_id: str | None = None) -> dict:
    payload = {"messages": messages, "userId": user_id}
    async with httpx.AsyncClient(base_url=MEMORY_SERVICE_URL, timeout=15.0) as client:
        r = await client.post(f"/memory/{agent_id}/add", json=payload)
        r.raise_for_status()
        return r.json()


async def search_memories(agent_id: str, query: str) -> list[dict]:
    async with httpx.AsyncClient(base_url=MEMORY_SERVICE_URL, timeout=10.0) as client:
        r = await client.get(f"/memory/{agent_id}/search", params={"q": query})
        r.raise_for_status()
        return r.json().get("results", [])


async def get_memory_hash(agent_id: str) -> dict:
    """Returns { hash, count, timestamp }. hash is "" if no memories yet."""
    async with httpx.AsyncClient(base_url=MEMORY_SERVICE_URL, timeout=10.0) as client:
        r = await client.get(f"/memory/{agent_id}/hash")
        r.raise_for_status()
        return r.json()
