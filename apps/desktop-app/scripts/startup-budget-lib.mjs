import path from 'node:path'

export const STARTUP_TIMING_PHASES = Object.freeze([
  'process_to_app_ready_ms',
  'app_ready_to_services_ready_ms',
  'services_ready_to_renderer_loaded_ms',
  'total_ms',
])

export function packagedExecutableCandidates({ platform, arch, releaseRoot }) {
  if (platform === 'darwin') {
    const directories = arch === 'arm64' ? ['mac-arm64', 'mac'] : ['mac', 'mac-x64']
    return directories.map((directory) => path.join(
      releaseRoot,
      directory,
      'Forge Harness Desktop.app',
      'Contents',
      'MacOS',
      'Forge Harness Desktop',
    ))
  }
  if (platform === 'win32') {
    const directories = arch === 'arm64'
      ? ['win-arm64-unpacked', 'win-unpacked']
      : ['win-unpacked', 'win-x64-unpacked']
    return directories.map((directory) => path.join(releaseRoot, directory, 'Forge Harness Desktop.exe'))
  }
  const directories = arch === 'arm64'
    ? ['linux-arm64-unpacked', 'linux-unpacked']
    : ['linux-unpacked', 'linux-x64-unpacked']
  return directories.map((directory) => path.join(releaseRoot, directory, 'harness-desktop'))
}

export function aggregateStartupSamples({
  executablePath,
  appRoot,
  samples,
  generatedAt = new Date(),
  expectedPlatform,
  expectedArch,
}) {
  if (samples.length === 0) throw new Error('At least one startup sample is required')
  samples.forEach((sample, index) => {
    validatePackagedStartupSample(sample, { expectedPlatform, expectedArch })
    if (index > 0 && !sameBudgets(sample.budgets_ms, samples[0].budgets_ms)) {
      throw new Error(`Startup sample ${index + 1} used different performance budgets`)
    }
  })
  const phases = STARTUP_TIMING_PHASES
  const budgets = samples[0].budgets_ms
  const p50 = Object.fromEntries(phases.map((phase) => [
    phase,
    percentile(samples.map((sample) => sample.timings_ms[phase]), 0.5),
  ]))
  const p95 = Object.fromEntries(phases.map((phase) => [
    phase,
    percentile(samples.map((sample) => sample.timings_ms[phase]), 0.95),
  ]))
  const violations = phases
    .filter((phase) => p95[phase] > budgets[phase])
    .map((phase) => ({
      phase,
      p95_ms: p95[phase],
      budget_ms: budgets[phase],
    }))

  return {
    schema_version: 1,
    generated_at: generatedAt.toISOString(),
    executable: path.relative(appRoot, executablePath),
    sample_count: samples.length,
    samples,
    p50_timings_ms: p50,
    p95_timings_ms: p95,
    budgets_ms: budgets,
    passed: violations.length === 0,
    violations,
  }
}

export function validatePackagedStartupSample(sample, { expectedPlatform, expectedArch } = {}) {
  if (!sample || typeof sample !== 'object') {
    throw new Error('Startup sample must be an object')
  }
  if (sample.schema_version !== 1) {
    throw new Error(`Unsupported startup report schema: ${String(sample.schema_version)}`)
  }
  if (sample.packaged !== true) {
    throw new Error('Startup report must come from a packaged desktop executable')
  }
  if (typeof sample.app_version !== 'string' || sample.app_version.length === 0) {
    throw new Error('Startup report app_version must be a non-empty string')
  }
  if (typeof sample.platform !== 'string' || sample.platform.length === 0) {
    throw new Error('Startup report platform must be a non-empty string')
  }
  if (typeof sample.arch !== 'string' || sample.arch.length === 0) {
    throw new Error('Startup report arch must be a non-empty string')
  }
  if (expectedPlatform && sample.platform !== expectedPlatform) {
    throw new Error(`Startup report platform ${String(sample.platform)} does not match host ${expectedPlatform}`)
  }
  if (expectedArch && sample.arch !== expectedArch) {
    throw new Error(`Startup report architecture ${String(sample.arch)} does not match host ${expectedArch}`)
  }
  if (!sample.timings_ms || !sample.budgets_ms) {
    throw new Error('Startup report must include timings_ms and budgets_ms')
  }
  if (sample.diagnostics_ms !== undefined) validateStartupDiagnostics(sample.diagnostics_ms)
  for (const phase of STARTUP_TIMING_PHASES) {
    if (!Number.isSafeInteger(sample.timings_ms[phase]) || sample.timings_ms[phase] < 0) {
      throw new Error(`Startup timing ${phase} must be a non-negative safe integer`)
    }
    if (!Number.isSafeInteger(sample.budgets_ms[phase]) || sample.budgets_ms[phase] <= 0) {
      throw new Error(`Startup budget ${phase} must be a positive safe integer`)
    }
  }
  const phaseTotal = STARTUP_TIMING_PHASES
    .filter((phase) => phase !== 'total_ms')
    .reduce((total, phase) => total + sample.timings_ms[phase], 0)
  if (Math.abs(phaseTotal - sample.timings_ms.total_ms) > 2) {
    throw new Error('Startup phase timings do not match total_ms')
  }
  const calculatedPass = STARTUP_TIMING_PHASES.every(
    (phase) => sample.timings_ms[phase] <= sample.budgets_ms[phase],
  )
  if (sample.passed !== calculatedPass) {
    throw new Error('Startup report passed flag does not match its timings and budgets')
  }
  if (!Array.isArray(sample.violations)) {
    throw new Error('Startup report violations must be an array')
  }
  const expectedViolations = STARTUP_TIMING_PHASES
    .filter((phase) => sample.timings_ms[phase] > sample.budgets_ms[phase])
    .map((phase) => ({
      phase,
      actual_ms: sample.timings_ms[phase],
      budget_ms: sample.budgets_ms[phase],
    }))
  if (JSON.stringify(sample.violations) !== JSON.stringify(expectedViolations)) {
    throw new Error('Startup report violations do not match its timings and budgets')
  }
}

function validateStartupDiagnostics(diagnostics) {
  if (!diagnostics || typeof diagnostics !== 'object' || Array.isArray(diagnostics)) {
    throw new Error('Startup diagnostics must be an object')
  }
  for (const [name, value] of Object.entries(diagnostics)) {
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new Error(`Startup diagnostic ${name} must be a non-negative safe integer`)
    }
  }
}

export function validateStartupAggregateReport(report, {
  expectedPlatform,
  expectedArch,
  expectedSampleCount,
  requirePassed = false,
} = {}) {
  if (!report || typeof report !== 'object') {
    throw new Error('Startup aggregate report must be an object')
  }
  if (report.schema_version !== 1) {
    throw new Error(`Unsupported startup aggregate schema: ${String(report.schema_version)}`)
  }
  if (typeof report.generated_at !== 'string' || Number.isNaN(Date.parse(report.generated_at))) {
    throw new Error('Startup aggregate generated_at must be an ISO timestamp')
  }
  if (typeof report.executable !== 'string' || report.executable.length === 0) {
    throw new Error('Startup aggregate executable must be a non-empty string')
  }
  if (!Array.isArray(report.samples) || report.samples.length === 0) {
    throw new Error('Startup aggregate samples must be a non-empty array')
  }
  if (report.sample_count !== report.samples.length) {
    throw new Error('Startup aggregate sample_count does not match samples')
  }
  if (expectedSampleCount !== undefined && report.sample_count !== expectedSampleCount) {
    throw new Error(
      `Startup aggregate requires ${expectedSampleCount} samples, received ${String(report.sample_count)}`,
    )
  }

  const expected = aggregateStartupSamples({
    executablePath: report.executable,
    appRoot: '.',
    samples: report.samples,
    generatedAt: new Date(report.generated_at),
    expectedPlatform,
    expectedArch,
  })
  for (const field of [
    'p50_timings_ms',
    'p95_timings_ms',
    'budgets_ms',
    'passed',
    'violations',
  ]) {
    if (JSON.stringify(report[field]) !== JSON.stringify(expected[field])) {
      throw new Error(`Startup aggregate ${field} does not match its samples`)
    }
  }
  if (requirePassed && report.passed !== true) {
    throw new Error('Startup aggregate exceeds its P95 budget')
  }

  const appVersions = new Set(report.samples.map((sample) => sample.app_version))
  if (appVersions.size !== 1) {
    throw new Error('Startup aggregate samples must use one app_version')
  }
  return {
    appVersion: report.samples[0].app_version,
    platform: report.samples[0].platform,
    arch: report.samples[0].arch,
  }
}

export function percentile(values, ratio) {
  if (values.length === 0) throw new Error('At least one percentile value is required')
  const sorted = [...values].sort((left, right) => left - right)
  const index = Math.max(0, Math.ceil(sorted.length * ratio) - 1)
  return sorted[index]
}

export function positiveInteger(rawValue, fallback, maximum) {
  if (!rawValue || !/^\d+$/.test(rawValue)) return fallback
  const parsed = Number(rawValue)
  return Number.isSafeInteger(parsed) && parsed > 0 && parsed <= maximum ? parsed : fallback
}

function sameBudgets(left, right) {
  return STARTUP_TIMING_PHASES.every((phase) => left[phase] === right[phase])
}
