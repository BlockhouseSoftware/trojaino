import { spawn } from "node:child_process";

spawn("node", ["--test", "tests"], { stdio: "inherit" });
