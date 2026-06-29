export const config = {
  port:        Number(process.env.TC_SIDECAR_PORT     ?? 4099),
  nodeHost:    process.env.TC_SIDECAR_NODE_HOST        ?? "https://node.tinycloud.xyz",
  privateKey:  process.env.TC_SIDECAR_PRIVATE_KEY      ?? "",
  dataDir:     process.env.TC_SIDECAR_DATA_DIR         ?? ".sidecar-data",
  // Override the node binary used to invoke the tc CLI (useful in Docker where
  // "node" is on PATH but process.execPath is bun). Defaults to "node".
  nodeBin:     process.env.TC_NODE_BIN                 ?? "node",
  tcSpace:     "applications",
  tcListenDb:  "xyz.tinycloud.listen/conversations",
} as const;
