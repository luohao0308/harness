import assert from 'node:assert/strict'
import test from 'node:test'

import {
  aggregateStartupSamples,
  packagedExecutableCandidates,
  percentile,
  positiveInteger,
  validatePackagedStartupSample,
} from './startup-budget-lib.mjs'

const budgets = {
  process_to_app_ready_ms: 2_000,
  app_ready_to_services_ready_ms: 1_500,
  services_ready_to_renderer_loaded_ms: 3_500,
  total_ms: 6_000,
}

function sample(totalMs, diagnostics = undefined) {
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
    app_version: '0.1.0',
    platform: 'darwin',
    arch: 'arm64',
    packaged: true,
    timings_ms: timings,
    budgets_ms: budgets,
    passed: violations.length === 0,
    violations,
    ...(diagnostics ? { diagnostics_ms: diagnostics } : {}),
  }
}

test('aggregates multiple samples and fails an exceeded P95 budget', () => {
  const report = aggregateStartupSamples({
    executablePath: '/workspace/release/mac/Forge Harness Desktop',
    appRoot: '/workspace',
    samples: [sample(2_000), sample(2_500), sample(6_500)],
    generatedAt: new Date('2026-07-31T00:00:00.000Z'),
    expectedPlatform: 'darwin',
    expectedArch: 'arm64',
  })

  assert.equal(report.sample_count, 3)
  assert.equal(report.p50_timings_ms.total_ms, 2_500)
  assert.equal(report.p95_timings_ms.total_ms, 6_500)
  assert.equal(report.passed, false)
  assert.deepEqual(report.violations, [
    {
      phase: 'services_ready_to_renderer_loaded_ms',
      p95_ms: 5_700,
      budget_ms: 3_500,
    },
    {
      phase: 'total_ms',
      p95_ms: 6_500,
      budget_ms: 6_000,
    },
  ])
})

test('retains per-sample diagnostics without including them in P95 budget calculations', () => {
  const firstDiagnostics = {
    sidecar_spawned_at_ms: 40,
    sidecar_ready_at_ms: 420,
    sidecar_startup_ms: 380,
  }
  const report = aggregateStartupSamples({
    executablePath: '/workspace/release/mac/Forge Harness Desktop',
    appRoot: '/workspace',
    samples: [sample(2_000, firstDiagnostics), sample(2_500, { renderer_load_ms: 2_200 })],
    generatedAt: new Date('2026-07-31T00:00:00.000Z'),
    expectedPlatform: 'darwin',
    expectedArch: 'arm64',
  })

  assert.deepEqual(report.samples[0].diagnostics_ms, firstDiagnostics)
  assert.deepEqual(report.samples[1].diagnostics_ms, { renderer_load_ms: 2_200 })
  assert.equal(report.passed, true)
  assert.equal(report.p95_timings_ms.total_ms, 2_500)
})

test('selects the host architecture before fallback package directories', () => {
  assert.deepEqual(
    packagedExecutableCandidates({
      platform: 'darwin',
      arch: 'arm64',
      releaseRoot: '/release',
    }),
    [
      '/release/mac-arm64/Forge Harness Desktop.app/Contents/MacOS/Forge Harness Desktop',
      '/release/mac/Forge Harness Desktop.app/Contents/MacOS/Forge Harness Desktop',
    ],
  )
})

test('validates numeric controls and nearest-rank percentiles', () => {
  assert.equal(positiveInteger('3', 1, 10), 3)
  assert.equal(positiveInteger('-1', 2, 10), 2)
  assert.equal(positiveInteger('20', 2, 10), 2)
  assert.equal(percentile([30, 10, 20], 0.5), 20)
  assert.equal(percentile([30, 10, 20], 0.95), 30)
})

test('rejects unpackaged, malformed, and architecture-mismatched reports', () => {
  assert.throws(
    () => validatePackagedStartupSample({ ...sample(2_000), packaged: false }),
    /packaged desktop executable/,
  )
  assert.throws(
    () => validatePackagedStartupSample({
      ...sample(2_000),
      timings_ms: { ...sample(2_000).timings_ms, total_ms: 2_100 },
    }),
    /do not match total_ms/,
  )
  assert.throws(
    () => validatePackagedStartupSample(sample(2_000), { expectedArch: 'x64' }),
    /does not match host x64/,
  )
  assert.throws(
    () => validatePackagedStartupSample({ ...sample(6_500), violations: [] }),
    /violations do not match/,
  )
})

test('rejects sample sets that do not use identical budgets', () => {
  const changedBudgetSample = sample(2_000)
  changedBudgetSample.budgets_ms = { ...budgets, total_ms: 7_000 }

  assert.throws(
    () => aggregateStartupSamples({
      executablePath: '/workspace/release/mac/Forge Harness Desktop',
      appRoot: '/workspace',
      samples: [sample(2_000), changedBudgetSample],
    }),
    /different performance budgets/,
  )
})
