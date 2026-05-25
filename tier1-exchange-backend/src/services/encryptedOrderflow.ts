export class EncryptedOrderflow {
  envelope(metadata: Record<string, unknown>): Record<string, unknown> {
    return {
      mode: "encrypted-orderflow",
      publicMetadataHash: stableHash(metadata),
      payloadEncrypted: Boolean(process.env.ORDERFLOW_ENCRYPTION_KEY_ID),
      keyId: process.env.ORDERFLOW_ENCRYPTION_KEY_ID ?? "not_configured",
    };
  }
}

function stableHash(value: Record<string, unknown>): string {
  const serialized = JSON.stringify(value, Object.keys(value).sort());
  let hash = 0;
  for (let index = 0; index < serialized.length; index += 1) {
    hash = (hash * 31 + serialized.charCodeAt(index)) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}
