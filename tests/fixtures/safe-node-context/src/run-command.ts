import { spawn } from "node:child_process";

spawn(request.body.command, { shell: true });
