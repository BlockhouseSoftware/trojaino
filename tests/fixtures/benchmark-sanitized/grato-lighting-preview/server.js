import fs from "node:fs";

export function removeTemporaryUpload(originalPath) {
  return fs.rm(originalPath, { force: true });
}
