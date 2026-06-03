"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { EventEmitter } = require("node:events");
const path = require("node:path");
const test = require("node:test");
const {
  buildUvArgs,
  missingProjectMessage,
  resolveProjectDir,
  run,
  uvMissingMessage,
} = require("../bin/hao.cjs");

test("buildUvArgs forwards hao args through uv project execution", () => {
  const projectDir = path.resolve("/tmp/harness/services/api-server");
  assert.deepEqual(buildUvArgs(["--cwd", "/work", "act", "fix bug"], projectDir), [
    "run",
    "--project",
    projectDir,
    "hao",
    "--cwd",
    "/work",
    "act",
    "fix bug",
  ]);
});

test("resolveProjectDir supports HAO_PYTHON_PROJECT override", () => {
  const override = path.resolve("/tmp/custom-api-server");
  assert.equal(resolveProjectDir({ HAO_PYTHON_PROJECT: override }, "/pkg/root"), override);
});

test("error messages explain missing uv and project recovery", () => {
  assert.match(uvMissingMessage("uv"), /Install uv/);
  assert.match(missingProjectMessage("/missing/project"), /HAO_PYTHON_PROJECT/);
});

test("run preserves caller cwd, forwards env, and propagates child exit code", () => {
  const originalExitCode = process.exitCode;
  process.exitCode = undefined;

  try {
    const projectDir = path.resolve(__dirname, "..");
    const env = {
      HAO_PYTHON_PROJECT: projectDir,
      HAO_UV_BIN: "/opt/bin/uv",
      HAO_TEST_MARKER: "kept",
    };
    const child = new EventEmitter();
    let captured = null;
    const result = run(["doctor"], env, (command, args, options) => {
      captured = { command, args, options };
      return child;
    });

    assert.equal(result, child);
    assert.equal(captured.command, "/opt/bin/uv");
    assert.deepEqual(captured.args, ["run", "--project", projectDir, "hao", "doctor"]);
    assert.equal(captured.options.cwd, process.cwd());
    assert.equal(captured.options.env, env);
    assert.equal(captured.options.stdio, "inherit");

    child.emit("exit", 7, null);
    assert.equal(process.exitCode, 7);
  } finally {
    process.exitCode = originalExitCode;
  }
});

test("run reports missing uv spawn failures", () => {
  const originalExitCode = process.exitCode;
  const originalConsoleError = console.error;
  process.exitCode = undefined;
  const errors = [];
  console.error = (message) => {
    errors.push(message);
  };

  try {
    const projectDir = path.resolve(__dirname, "..");
    const child = new EventEmitter();
    const result = run(
      ["--help"],
      {
        HAO_PYTHON_PROJECT: projectDir,
        HAO_UV_BIN: "/missing/uv",
      },
      () => child,
    );

    assert.equal(result, child);
    child.emit("error", Object.assign(new Error("spawn /missing/uv ENOENT"), { code: "ENOENT" }));
    assert.equal(process.exitCode, 1);
    assert.match(errors.join("\n"), /could not execute "\/missing\/uv"/);
    assert.match(errors.join("\n"), /HAO_UV_BIN/);
  } finally {
    console.error = originalConsoleError;
    process.exitCode = originalExitCode;
  }
});

test("entrypoint exits non-zero when the Python project is missing", () => {
  const missingProject = path.join(
    "/tmp",
    `hao-launcher-missing-project-${process.pid}-${Date.now()}`,
  );
  const result = spawnSync(process.execPath, [path.resolve(__dirname, "../bin/hao.cjs"), "--help"], {
    encoding: "utf8",
    env: {
      ...process.env,
      HAO_PYTHON_PROJECT: missingProject,
    },
  });

  assert.equal(result.status, 1);
  assert.match(result.stderr, /could not find the bundled Python project/);
  assert.match(result.stderr, /HAO_PYTHON_PROJECT/);
});
