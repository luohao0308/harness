import { spawn } from "node:child_process";

const HOST = "127.0.0.1";
const PORT = "5177";
const BASE_URL = `http://${HOST}:${PORT}`;
const TEST_FILES = [
  "e2e/agent-workspace.smoke.spec.ts",
  "e2e/agent-workspace-success.smoke.spec.ts",
  "e2e/run-detail.smoke.spec.ts",
  "e2e/agent-studio.smoke.spec.ts",
  "e2e/eval-page.smoke.spec.ts",
  "e2e/observability.smoke.spec.ts",
  "e2e/knowledge-demo.smoke.spec.ts",
  "e2e/tools-page.smoke.spec.ts",
  "e2e/sandboxes-page.smoke.spec.ts",
  "e2e/nav-resilience.spec.ts",
];

const npmCommand = process.platform === "win32" ? "npx.cmd" : "npx";

function spawnProcess(command, args, options = {}) {
  return spawn(command, args, {
    stdio: "inherit",
    ...options,
  });
}

async function isServerReady() {
  try {
    const response = await fetch(BASE_URL);
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer(process, timeoutMs = 60_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (process.exitCode !== null) {
      throw new Error(`Vite exited before ${BASE_URL} became ready.`);
    }
    if (await isServerReady()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${BASE_URL}.`);
}

async function run() {
  let server = null;
  if (!(await isServerReady())) {
    server = spawnProcess(npmCommand, [
      "vite",
      "--host",
      HOST,
      "--port",
      PORT,
      "--strictPort",
    ]);
    await waitForServer(server);
  }

  const childEnv = {
    ...process.env,
    HARNESS_PLAYWRIGHT_EXTERNAL_SERVER: "1",
  };
  const playwright = spawnProcess(
    npmCommand,
    ["playwright", "test", "--project=chromium", ...TEST_FILES, ...process.argv.slice(2)],
    { env: childEnv },
  );

  const exitCode = await new Promise((resolve) => {
    playwright.on("exit", (code) => resolve(code ?? 1));
  });

  if (server !== null) {
    server.kill("SIGTERM");
  }

  process.exit(exitCode);
}

run().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
