import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { config } from "./config.ts";

export interface StoredDelegation {
  /** The delegation candidate JSON consumed by `tc kv get --delegation <file>`. */
  serialized: string;
  ownerDid: string;
  grantedAt: string;
  expiresAt: string | null;
}

// Single-owner store: DealProof reads from one Listen instance, so only one
// delegation is ever stored. File is at $TC_SIDECAR_DATA_DIR/delegation.json:
//   local dev  → .sidecar-data/delegation.json  (gitignored)
//   Phala TEE  → /data/delegation.json           (Docker volume)
const STORE_PATH = join(config.dataDir, "delegation.json");

export function loadDelegation(): StoredDelegation | null {
  if (!existsSync(STORE_PATH)) return null;
  try {
    return JSON.parse(readFileSync(STORE_PATH, "utf-8")) as StoredDelegation;
  } catch {
    return null;
  }
}

export function saveDelegation(record: StoredDelegation): void {
  mkdirSync(dirname(STORE_PATH), { recursive: true });
  writeFileSync(STORE_PATH, JSON.stringify(record, null, 2), {
    encoding: "utf-8",
    mode: 0o600,
  });
}
