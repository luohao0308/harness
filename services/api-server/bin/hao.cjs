#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

function resolvePackageRoot(startDir = __dirname) {
  return path.resolve(startDir, "..");
}

function resolveProjectDir(env = process.env, packageRoot = resolvePackageRoot()) {
  const override = (env.HAO_PYTHON_PROJECT || "").trim();
  if (override) {
    return path.resolve(override);
  }
  return packageRoot;
}

function buildUvArgs(argv, projectDir) {
  return ["run", "--project", projectDir, "hao", ...argv];
}

function missingProjectMessage(projectDir) {
  return [
    "hao npm launcher could not find the bundled Python project.",
    `Expected pyproject.toml at: ${path.join(projectDir, "pyproject.toml")}`,
    "If you are developing locally, set HAO_PYTHON_PROJECT=/path/to/services/api-server.",
  ].join("\n");
}

function uvMissingMessage(uvBin) {
  return [
    `hao npm launcher could not execute "${uvBin}".`,
    "Install uv and make it available on PATH: https://docs.astral.sh/uv/getting-started/installation/",
    "Or set HAO_UV_BIN=/absolute/path/to/uv.",
  ].join("\n");
}

function run(argv = process.argv.slice(2), env = process.env, spawnImpl = spawn) {
  const packageRoot = resolvePackageRoot();
  const projectDir = resolveProjectDir(env, packageRoot);
  const pyproject = path.join(projectDir, "pyproject.toml");
  if (!fs.existsSync(pyproject)) {
    console.error(missingProjectMessage(projectDir));
    return 1;
  }

  const uvBin = (env.HAO_UV_BIN || "uv").trim() || "uv";
  const child = spawnImpl(uvBin, buildUvArgs(argv, projectDir), {
    cwd: process.cwd(),
    env,
    stdio: "inherit",
  });

  child.on("error", (error) => {
    if (error && error.code === "ENOENT") {
      console.error(uvMissingMessage(uvBin));
    } else {
      console.error(`hao npm launcher failed: ${error.message}`);
    }
    process.exitCode = 1;
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exitCode = code === null ? 1 : code;
  });

  return child;
}

if (require.main === module) {
  const result = run();
  if (typeof result === "number") {
    process.exitCode = result;
  }
}

module.exports = {
  buildUvArgs,
  missingProjectMessage,
  resolvePackageRoot,
  resolveProjectDir,
  run,
  uvMissingMessage,
};
