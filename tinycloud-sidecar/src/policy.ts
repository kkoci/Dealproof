export interface PermissionEntry {
  service: string;
  space?: string;
  path: string;
  actions: string[];
  skipPrefix?: boolean;
  description?: string;
}

/**
 * The permissions the Listen data owner must delegate to this sidecar's DID.
 * Advertised via GET /internal/policy so the operator knows exactly what to grant.
 */
export function backendPolicy(): PermissionEntry[] {
  return [
    {
      service: "tinycloud.kv",
      space: "applications",
      path: "xyz.tinycloud.listen/transcript/",
      actions: ["get"],
      skipPrefix: true,
      description: "Read per-conversation transcript KV blobs from TinyCloud Listen.",
    },
    {
      service: "tinycloud.kv",
      space: "applications",
      path: "xyz.tinycloud.listen/conversations",
      actions: ["get"],
      skipPrefix: true,
      description: "Read conversation metadata rows via SQL.",
    },
  ];
}
