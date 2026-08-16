import assert from 'node:assert/strict'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { aggregateStartupSamples } from './startup-budget-lib.mjs'
import {
  EXPECTED_DESKTOP_STARTUP_ARTIFACTS,
  validateStartupEvidenceArtifacts,
} from './startup-evidence-lib.mjs'

const budgets = {
  process_to_app_ready_ms: 2_000,
  app_ready_to_services_ready_ms: 1_500,
  services_ready_to_renderer_loaded_ms: 3_500,
  total_ms: 6_000,
}

test('validates one five-sample passing report per release artifact', async () => {
  await withEvidenceRoot(async (rootPath) => {
    await writeEvidenceSet(rootPath)

    const summary = await validateStartupEvidenceArtifacts(rootPath, {
      releaseRef: 'v1.2.3',
      generatedAt: new Date('2026-08-17T00:00:00.000Z'),
    })

    assert.equal(summary.passed, true)
    assert.equal(summary.release_ref, 'v1.2.3')
    assert.equal(summary.reports.length, 3)
    assert.deepEqual(
      summary.reports.map((report) => `${report.platform}/${report.arch}`).sort(),
      ['darwin/x64', 'linux/x64', 'win32/x64'],
    )
  })
})

test('rejects missing and duplicate release reports', async () => {
  await withEvidenceRoot(async (rootPath) => {
    await writeEvidenceSet(rootPath, { skipArtifact: 'harness-desktop-linux' })
    await assert.rejects(
      validateStartupEvidenceArtifacts(rootPath),
      /must be exactly/,
    )
  })

  await withEvidenceRoot(async (rootPath) => {
    await writeEvidenceSet(rootPath)
    const duplicateRoot = path.join(rootPath, 'harness-desktop-mac', 'duplicate')
    await mkdir(duplicateRoot)
    await writeFile(
      path.join(duplicateRoot, 'startup-budget-report-darwin-x64.json'),
      `${JSON.stringify(startupReport('darwin', 'x64'))}\n`,
    )
    await assert.rejects(
      validateStartupEvidenceArtifacts(rootPath),
      /exactly one startup report/,
    )
  })
})

test('rejects wrong platform identity and non-five-sample reports', async () => {
  await withEvidenceRoot(async (rootPath) => {
    await writeEvidenceSet(rootPath, {
      reportOverrides: {
        'harness-desktop-win': startupReport('linux', 'x64'),
      },
    })
    await assert.rejects(
      validateStartupEvidenceArtifacts(rootPath),
      /does not match host win32/,
    )
  })

  await withEvidenceRoot(async (rootPath) => {
    await writeEvidenceSet(rootPath, {
      reportOverrides: {
        'harness-desktop-linux': startupReport('linux', 'x64', { sampleCount: 4 }),
      },
    })
    await assert.rejects(
      validateStartupEvidenceArtifacts(rootPath),
      /requires 5 samples/,
    )
  })
})

test('rejects P95 failures and cross-platform app version drift', async () => {
  await withEvidenceRoot(async (rootPath) => {
    await writeEvidenceSet(rootPath, {
      reportOverrides: {
        'harness-desktop-mac': startupReport('darwin', 'x64', { totals: [2_000, 2_100, 2_200, 2_300, 6_500] }),
      },
    })
    await assert.rejects(
      validateStartupEvidenceArtifacts(rootPath),
      /exceeds its P95 budget/,
    )
  })

  await withEvidenceRoot(async (rootPath) => {
    await writeEvidenceSet(rootPath, {
      reportOverrides: {
        'harness-desktop-win': startupReport('win32', 'x64', { appVersion: '9.9.9' }),
      },
    })
    await assert.rejects(
      validateStartupEvidenceArtifacts(rootPath),
      /must use one app_version/,
    )
  })
})

async function withEvidenceRoot(callback) {
  const rootPath = await mkdtemp(path.join(os.tmpdir(), 'harness-startup-evidence-'))
  try {
    await callback(rootPath)
  } finally {
    await rm(rootPath, { recursive: true, force: true })
  }
}

async function writeEvidenceSet(rootPath, { skipArtifact, reportOverrides = {} } = {}) {
  for (const expected of EXPECTED_DESKTOP_STARTUP_ARTIFACTS) {
    if (expected.artifact === skipArtifact) continue
    const artifactRoot = path.join(rootPath, expected.artifact)
    await mkdir(artifactRoot)
    const report = reportOverrides[expected.artifact]
      || startupReport(expected.platform, expected.arch)
    await writeFile(
      path.join(artifactRoot, `startup-budget-report-${expected.platform}-${expected.arch}.json`),
      `${JSON.stringify(report)}\n`,
    )
  }
}

function startupReport(platform, arch, {
  appVersion = '1.2.3',
  sampleCount = 5,
  totals = Array.from({ length: sampleCount }, (_, index) => 2_000 + (index * 100)),
} = {}) {
  const samples = totals.map((totalMs) => startupSample(platform, arch, appVersion, totalMs))
  return aggregateStartupSamples({
    executablePath: `/release/${platform}-${arch}/harness-desktop`,
    appRoot: '/release',
    samples,
    generatedAt: new Date('2026-08-17T00:00:00.000Z'),
    expectedPlatform: platform,
    expectedArch: arch,
  })
}

function startupSample(platform, arch, appVersion, totalMs) {
  const timings = {
    process_to_app_ready_ms: 500,
    app_ready_to_services_ready_ms: 300,
    services_ready_to_renderer_loaded_ms: totalMs - 800,
    total_ms: totalMs,
  }
  const violations = Object.keys(timings)
    .filter((phase) => timings[phase] > budgets[phase])
    .map((phase) => ({ phase, actual_ms: timings[phase], budget_ms: budgets[phase] }))
  return {
    schema_version: 1,
    app_version: appVersion,
    platform,
    arch,
    packaged: true,
    timings_ms: timings,
    budgets_ms: budgets,
    passed: violations.length === 0,
    violations,
  }
}
