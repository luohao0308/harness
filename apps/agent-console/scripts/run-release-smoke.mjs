import { spawn } from "node:child_process";
import { access } from "node:fs/promises";

const HOST = "127.0.0.1";
const PORT = "5177";
const BASE_URL = `http://${HOST}:${PORT}`;
const PHASE0B_EVIDENCE_PATH =
  "../../.omx/reports/complete-harness-validation-flow/phase0b-release-spine-evidence.json";
const ALLOW_MISSING_PHASE0B_EVIDENCE =
  process.env.HARNESS_ALLOW_MISSING_PHASE0B_EVIDENCE === "1";
const TEST_FILES = [
  "e2e/agent-workspace.smoke.spec.ts",
  "e2e/agent-workspace-success.smoke.spec.ts",
  "e2e/run-detail.smoke.spec.ts",
  "e2e/team-mode.smoke.spec.ts",
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
  try {
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
      playwright.on("error", () => resolve(1));
    });

    if (exitCode === 0) {
      await validatePhase0bEvidence();
    }

    process.exitCode = exitCode;
  } finally {
    if (server !== null) {
      server.kill("SIGTERM");
    }
  }
}

async function validatePhase0bEvidence() {
  try {
    await access(PHASE0B_EVIDENCE_PATH);
  } catch {
    if (ALLOW_MISSING_PHASE0B_EVIDENCE) {
      console.warn(
        "Phase 0b release spine evidence is missing; continuing because HARNESS_ALLOW_MISSING_PHASE0B_EVIDENCE=1.",
      );
      return;
    }
    throw new Error(
      "Phase 0b release spine evidence is required for release smoke. " +
        "Write .omx/reports/complete-harness-validation-flow/phase0b-release-spine-evidence.json " +
        "or set HARNESS_ALLOW_MISSING_PHASE0B_EVIDENCE=1 for local partial runs.",
    );
  }

  const checker = spawnProcess(
    process.platform === "win32" ? "py" : "python3",
    [
      "../../scripts/check-release-spine-evidence.py",
      PHASE0B_EVIDENCE_PATH,
    ],
    { cwd: new URL("..", import.meta.url).pathname },
  );

  const exitCode = await new Promise((resolve) => {
    checker.on("exit", (code) => resolve(code ?? 1));
    checker.on("error", () => resolve(1));
  });
  if (exitCode !== 0) {
    throw new Error("Phase 0b release spine evidence validation failed.");
  }
}

run().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
