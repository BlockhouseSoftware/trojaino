import { spawn } from "child_process";

export function runSmokeTests() {
  return spawn("node", ["--test", "tests/core.test.js"]);
}
