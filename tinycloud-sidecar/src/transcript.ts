import { execFile } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

import { config } from "./config.ts";
import { loadDelegation } from "./delegation-store.ts";

const execFileAsync = promisify(execFile);

// Resolve the tc CLI entrypoint once at startup. The tc package ships its own
// dist/index.js; we run it explicitly with `node` rather than relying on a
// global `tc` install. Same pattern as git-haiku TcCliSecretsProvider.
function resolveTcEntry(): string {
  const require = createRequire(import.meta.url);
  const pkgJson = require.resolve("@tinycloud/cli/package.json");
  const dir = pkgJson.slice(0, pkgJson.lastIndexOf("/"));
  return join(dir, "dist", "index.js");
}

const TC_ENTRY = resolveTcEntry();

// Error shape from promisify(execFile) when process exits non-zero
interface ExecError extends Error {
  stderr?: string;
  stdout?: string;
  code?: number;
}

/**
 * Write the stored delegation to a 0700 temp dir, call fn with the file path,
 * and delete the dir in finally. Throws "no-delegation" if nothing is stored.
 */
async function withDelegationFile<T>(fn: (filePath: string) => Promise<T>): Promise<T> {
  const stored = loadDelegation();
  if (!stored) throw new Error("no-delegation");

  const dir = mkdtempSync(join(tmpdir(), "dealproof-deleg-"));
  const file = join(dir, "delegation.json");
  writeFileSync(file, stored.serialized, { encoding: "utf-8", mode: 0o600 });

  try {
    return await fn(file);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * Fetch the sentence array for one conversation via `tc kv get`.
 * Returns null on NOT_FOUND. Throws on all other tc failures.
 */
export async function fetchTranscript(conversationId: string): Promise<unknown[] | null> {
  const key = `xyz.tinycloud.listen/transcript/${conversationId}`;

  let stdout: string;
  try {
    ({ stdout } = await withDelegationFile((delegFile) =>
      execFileAsync(
        config.nodeBin,
        [
          TC_ENTRY,
          "kv", "get", key,
          "--space",      config.tcSpace,
          "--raw",
          "--delegation", delegFile,
          "--host",       config.nodeHost,
        ],
        {
          env: { ...process.env, TC_PRIVATE_KEY: config.privateKey },
          maxBuffer: 10 * 1024 * 1024,
        },
      )
    ));
  } catch (err: unknown) {
    const e = err as ExecError;
    const combined = (e.stderr ?? "") + (e.stdout ?? "") + String(e.message ?? "");
    if (combined.includes("NOT_FOUND")) return null;
    throw new Error(`tc kv get failed for ${conversationId}: ${(e.stderr ?? String(err)).slice(0, 300)}`);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return null; // empty or non-JSON KV value — treat as missing
  }

  // Unwrap if tc wraps in { value: [...] } or { data: [...] }
  if (parsed && !Array.isArray(parsed) && typeof parsed === "object") {
    const obj = parsed as Record<string, unknown>;
    if (Array.isArray(obj["value"])) return obj["value"] as unknown[];
    if (Array.isArray(obj["data"]))  return obj["data"]  as unknown[];
    if ("NOT_FOUND" in obj)          return null;
  }

  return Array.isArray(parsed) ? parsed : null;
}

/**
 * Fetch conversation metadata rows via `tc sql query`.
 * Returns rows as plain objects (columns zipped from the tc --json output).
 */
export async function fetchConversations(limit = 300): Promise<Record<string, unknown>[]> {
  const query = `SELECT id, title, source, started_at, summary FROM conversation LIMIT ${limit}`;

  let stdout: string;
  try {
    ({ stdout } = await withDelegationFile((delegFile) =>
      execFileAsync(
        config.nodeBin,
        [
          TC_ENTRY,
          "sql", "query", query,
          "--db",         config.tcListenDb,
          "--space",      config.tcSpace,
          "--json",
          "--delegation", delegFile,
          "--host",       config.nodeHost,
        ],
        {
          env: { ...process.env, TC_PRIVATE_KEY: config.privateKey },
          maxBuffer: 10 * 1024 * 1024,
        },
      )
    ));
  } catch (err: unknown) {
    const e = err as ExecError;
    throw new Error(`tc sql query failed: ${(e.stderr ?? String(err)).slice(0, 300)}`);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    throw new Error("tc sql query: non-JSON output");
  }

  // tc --json returns { columns: string[], rows: unknown[][] }; zip to dicts.
  const raw = parsed as { columns?: string[]; rows?: unknown[][] };
  const columns = raw.columns ?? [];
  return (raw.rows ?? []).map((row) =>
    Object.fromEntries(columns.map((col, i) => [col, (row as unknown[])[i]]))
  );
}
