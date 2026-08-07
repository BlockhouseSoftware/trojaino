import fs from "node:fs/promises";

export async function cleanupTemporaryUpload(originalPath: string) {
  await fs.rm(originalPath, { force: true });
}
