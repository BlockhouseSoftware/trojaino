// Model Context Protocol tool server
import { exec } from "child_process";
import fs from "fs";

export function readSecrets() {
  return fs.readFileSync(process.env.HOME + "/.aws/credentials", "utf8");
}

export function shell(cmd: string) {
  return exec(cmd);
}
