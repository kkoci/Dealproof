import { privateKeyToAccount } from "viem/accounts";
import type { Hex } from "viem";
import { config } from "./config.ts";

/**
 * Return the sidecar's stable did:pkh from TC_SIDECAR_PRIVATE_KEY.
 *
 * In local dev: set TC_SIDECAR_PRIVATE_KEY in .env.
 * In Phala TEE:  set it as a secure environment variable on the CVM — the key
 *                never appears in logs or the image layer; it is injected at
 *                runtime by the Phala dashboard.
 *
 * A future upgrade can derive this key from dstack.getKey() inside the enclave
 * (same pattern as git-haiku identity.ts) once the /var/run/dstack.sock mount
 * is confirmed available on this CVM. For now env var is sufficient and matches
 * how every other secret (ANTHROPIC_API_KEY etc.) is handled in DealProof.
 */
export function getBackendDid(): string {
  if (!config.privateKey) {
    throw new Error(
      "TC_SIDECAR_PRIVATE_KEY is required. " +
      "Set it in .env for local dev or as a secure CVM env var on Phala.",
    );
  }
  const account = privateKeyToAccount(config.privateKey as Hex);
  return `did:pkh:eip155:1:${account.address}`;
}
