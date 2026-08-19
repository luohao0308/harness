import { spawn } from 'node:child_process'
import { access, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  aggregateStartupSamples,
  packagedExecutableCandidates,
  positiveInteger,
  validatePackagedStartupSample,
} from './startup-budget-lib.mjs'

const REPORT_PREFIX = 'HARNESS_DESKTOP_STARTUP_REPORT '
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const appRoot = path.resolve(__dirname, '..')
const releaseRoot = path.join(appRoot, 'release')
const sampleCount = positiveInteger(process.env.HARNESS_DESKTOP_STARTUP_SAMPLES, 5, 10)
const timeoutMs = positiveInteger(process.env.HARNESS_DESKTOP_STARTUP_TIMEOUT_MS, 30_000, 120_000)
const reportPath = path.resolve(
  process.env.HARNESS_DESKTOP_STARTUP_REPORT_PATH
    || path.join(appRoot, 'dist', `startup-budget-report-${process.platform}-${process.arch}.json`),
)

const executable = await resolvePackagedExecutable()
const samples = []

for (let index = 0; index < sampleCount; index += 1) {
  const sample = await runPackagedStartup(executable, index + 1)
  samples.push(sample)
  process.stdout.write(
    `Desktop startup sample ${index + 1}/${sampleCount}: ${sample.timings_ms.total_ms} ms\n`,
  )
}

const report = aggregateStartupSamples({
  executablePath: executable,
  appRoot,
  samples,
  expectedPlatform: process.platform,
  expectedArch: process.arch,
})
await mkdir(path.dirname(reportPath), { recursive: true })
await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')

if (!report.passed) {
  process.stderr.write(`Desktop startup budget failed: ${JSON.stringify(report.violations)}\n`)
  process.stderr.write(`Startup report: ${reportPath}\n`)
  process.exitCode = 1
} else {
  process.stdout.write(
    `Desktop startup budget passed: P95 ${report.p95_timings_ms.total_ms} ms <= ${report.budgets_ms.total_ms} ms\n`,
  )
  process.stdout.write(`Startup report: ${reportPath}\n`)
}

async function resolvePackagedExecutable() {
  if (process.env.HARNESS_DESKTOP_EXECUTABLE) {
    const configured = path.resolve(process.env.HARNESS_DESKTOP_EXECUTABLE)
    await access(configured)
    return configured
  }

  const candidates = packagedExecutableCandidates({
    platform: process.platform,
    arch: process.arch,
    releaseRoot,
  })
  for (const candidate of candidates) {
    try {
      await access(candidate)
      return candidate
    } catch {
      // Continue to the next architecture-compatible electron-builder output.
    }
  }
  throw new Error(
    `Packaged Forge Harness Desktop executable not found. Run "npm run package" first. Checked: ${candidates.join(', ')}`,
  )
}

async function runPackagedStartup(executablePath, sampleNumber) {
  const userDataRoot = await mkdtemp(path.join(os.tmpdir(), `harness-startup-${sampleNumber}-`))
  try {
    return await new Promise((resolve, reject) => {
      const child = spawn(
        executablePath,
        [
          '--startup-budget-smoke',
          `--user-data-dir=${userDataRoot}`,
        ],
        {
          cwd: appRoot,
          env: {
            ...process.env,
            ELECTRON_RUN_AS_NODE: '',
            HARNESS_DESKTOP_OPEN_DEVTOOLS: '0',
            HARNESS_DESKTOP_STARTUP_BUDGET_MODE: '1',
            NO_PROXY: 'localhost,127.0.0.1',
          },
          stdio: ['ignore', 'pipe', 'pipe'],
        },
      )
      let stdout = ''
      let stderr = ''
      let timedOut = false
      const timeout = setTimeout(() => {
        timedOut = true
        child.kill('SIGKILL')
      }, timeoutMs)

      child.stdout.on('data', (chunk) => {
        stdout += chunk.toString()
      })
      child.stderr.on('data', (chunk) => {
        stderr += chunk.toString()
      })
      child.once('error', (error) => {
        clearTimeout(timeout)
        reject(timedOut
          ? new Error(`Packaged desktop startup timed out after ${timeoutMs} ms`)
          : error)
      })
      child.once('close', (code, signal) => {
        clearTimeout(timeout)
        if (timedOut) {
          reject(new Error(`Packaged desktop startup timed out after ${timeoutMs} ms`))
          return
        }
        const reportLine = stdout
          .split(/\r?\n/)
          .find((line) => line.startsWith(REPORT_PREFIX))
        if (!reportLine) {
          reject(new Error(
            `Packaged desktop exited with code ${code ?? 'unknown'}${signal ? ` (${signal})` : ''} without a startup report. stderr: ${stderr.slice(-2_000)}`,
          ))
          return
        }
        try {
          const report = JSON.parse(reportLine.slice(REPORT_PREFIX.length))
          validatePackagedStartupSample(report, {
            expectedPlatform: process.platform,
            expectedArch: process.arch,
          })
          const expectedExitCode = report.passed ? 0 : 1
          if (code !== expectedExitCode || signal) {
            reject(new Error(
              `Packaged desktop startup report expected exit code ${expectedExitCode}, received ${code ?? 'unknown'}${signal ? ` (${signal})` : ''}`,
            ))
            return
          }
          resolve(report)
        } catch (error) {
          reject(new Error(`Invalid packaged desktop startup report: ${String(error)}`))
        }
      })
    })
  } finally {
    await rm(userDataRoot, { recursive: true, force: true })
  }
}
