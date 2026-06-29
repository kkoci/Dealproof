import { config } from "./config.ts";
import { getBackendDid } from "./identity.ts";
import { loadDelegation, saveDelegation, type StoredDelegation } from "./delegation-store.ts";
import { backendPolicy } from "./policy.ts";
import { fetchConversations, fetchTranscript } from "./transcript.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function err(message: string, status = 500): Response {
  return json({ error: message }, status);
}

// ---------------------------------------------------------------------------
// Route handlers
// ---------------------------------------------------------------------------

async function handleDelegations(req: Request): Promise<Response> {
  let body: { serialized?: string; ownerDid?: string; expiresAt?: string | null };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return err("invalid JSON body", 400);
  }

  if (!body.serialized || !body.ownerDid) {
    return err("serialized and ownerDid are required", 400);
  }

  const record: StoredDelegation = {
    serialized: body.serialized,
    ownerDid:   body.ownerDid,
    grantedAt:  new Date().toISOString(),
    expiresAt:  body.expiresAt ?? null,
  };

  try {
    saveDelegation(record);
  } catch (e: unknown) {
    return err(`failed to store delegation: ${String(e)}`);
  }

  let did: string;
  try {
    did = getBackendDid();
  } catch (e: unknown) {
    return err(`delegation stored but could not derive backend DID: ${String(e)}`);
  }

  return json({ ok: true, did });
}

async function handleConversations(req: Request): Promise<Response> {
  if (loadDelegation() === null) {
    return err("no delegation stored — POST /internal/delegations first", 503);
  }

  const url   = new URL(req.url);
  const limit = Math.min(Number(url.searchParams.get("limit") ?? 300), 1000);

  try {
    const rows = await fetchConversations(limit);
    return json({ rows });
  } catch (e: unknown) {
    const msg = String(e);
    if (msg.includes("no-delegation")) {
      return err("no delegation stored — POST /internal/delegations first", 503);
    }
    return err(`tc sql query failed: ${msg}`, 502);
  }
}

async function handleTranscript(conversationId: string): Promise<Response> {
  if (!conversationId) return err("conversation ID is required", 400);

  if (loadDelegation() === null) {
    return err("no delegation stored — POST /internal/delegations first", 503);
  }

  try {
    const sentences = await fetchTranscript(conversationId);
    if (sentences === null) {
      return json({ error: "NOT_FOUND", id: conversationId }, 404);
    }
    return json(sentences);
  } catch (e: unknown) {
    const msg = String(e);
    if (msg.includes("no-delegation")) {
      return err("no delegation stored — POST /internal/delegations first", 503);
    }
    return err(`tc kv get failed: ${msg}`, 502);
  }
}

// ---------------------------------------------------------------------------
// Server
// ---------------------------------------------------------------------------

Bun.serve({
  port: config.port,
  hostname: "0.0.0.0",

  async fetch(req) {
    const url  = new URL(req.url);
    const path = url.pathname;

    if (path === "/health") {
      const hasDelegation = loadDelegation() !== null;
      return json({ ok: true, hasDelegation });
    }

    if (path === "/internal/policy") {
      return json(backendPolicy());
    }

    if (req.method === "POST" && path === "/internal/delegations") {
      return handleDelegations(req);
    }

    if (req.method === "GET" && path === "/internal/conversations") {
      return handleConversations(req);
    }

    if (req.method === "GET" && path.startsWith("/internal/transcript/")) {
      const conversationId = decodeURIComponent(path.slice("/internal/transcript/".length));
      return handleTranscript(conversationId);
    }

    return json({ error: `${req.method} ${path} not found` }, 404);
  },
});

console.log(`[tc-sidecar] listening on 0.0.0.0:${config.port}`);
console.log(`[tc-sidecar] node host: ${config.nodeHost}`);
console.log(`[tc-sidecar] delegation stored: ${loadDelegation() !== null}`);
