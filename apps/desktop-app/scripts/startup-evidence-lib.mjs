import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'

import { validateStartupAggregateReport } from './startup-budget-lib.mjs'

export const EXPECTED_DESKTOP_STARTUP_ARTIFACTS = Object.freeze([
  Object.freeze({ artifact: 'harness-desktop-mac', platform: 'darwin', arch: 'x64' }),
  Object.freeze({ artifact: 'harness-desktop-win', platform: 'win32', arch: 'x64' }),
  Object.freeze({ artifact: 'harness-desktop-linux', platform: 'linux', arch: 'x64' }),
])

export async function validateStartupEvidenceArtifacts(rootPath, {
  expectedArtifacts = EXPECTED_DESKTOP_STARTUP_ARTIFACTS,
  expectedSampleCount = 5,
  releaseRef = null,
  generatedAt = new Date(),
} = {}) {
  const rootEntries = await readdir(rootPath, { withFileTypes: true })
  const actualArtifacts = rootEntries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
  const expectedArtifactNames = expectedArtifacts.map((entry) => entry.artifact).sort()
  if (JSON.stringify(actualArtifacts) !== JSON.stringify(expectedArtifactNames)) {
    throw new Error(
      `Desktop startup artifacts must be exactly ${expectedArtifactNames.join(', ')}; received ${actualArtifacts.join(', ') || 'none'}`,
    )
  }

  const reports = []
  const identities = new Set()
  const appVersions = new Set()
  for (const expected of expectedArtifacts) {
    const artifactRoot = path.join(rootPath, expected.artifact)
    const reportPaths = (await findReportFiles(artifactRoot)).sort()
    if (reportPaths.length !== 1) {
      throw new Error(
        `${expected.artifact} must contain exactly one startup report; received ${reportPaths.length}`,
      )
    }
    const reportPath = reportPaths[0]
    const expectedFileName = `startup-budget-report-${expected.platform}-${expected.arch}.json`
    if (path.basename(reportPath) !== expectedFileName) {
      throw new Error(`${expected.artifact} startup report must be named ${expectedFileName}`)
    }

    const report = await readJson(reportPath)
    const identity = validateStartupAggregateReport(report, {
      expectedPlatform: expected.platform,
      expectedArch: expected.arch,
      expectedSampleCount,
      requirePassed: true,
    })
    const identityKey = `${identity.platform}/${identity.arch}`
    if (identities.has(identityKey)) {
      throw new Error(`Duplicate desktop startup identity: ${identityKey}`)
    }
    identities.add(identityKey)
    appVersions.add(identity.appVersion)
    reports.push({
      artifact: expected.artifact,
      file: path.relative(rootPath, reportPath),
      platform: identity.platform,
      arch: identity.arch,
      app_version: identity.appVersion,
      sample_count: report.sample_count,
      p95_timings_ms: report.p95_timings_ms,
      budgets_ms: report.budgets_ms,
      passed: report.passed,
    })
  }
  if (appVersions.size !== 1) {
    throw new Error('Desktop startup artifacts must use one app_version')
  }

  return {
    schema_version: 1,
    generated_at: generatedAt.toISOString(),
    release_ref: releaseRef,
    app_version: reports[0].app_version,
    expected_sample_count: expectedSampleCount,
    passed: true,
    reports,
  }
}

async function findReportFiles(rootPath) {
  const matches = []
  for (const entry of await readdir(rootPath, { withFileTypes: true })) {
    const entryPath = path.join(rootPath, entry.name)
    if (entry.isDirectory()) {
      matches.push(...await findReportFiles(entryPath))
    } else if (entry.isFile() && /^startup-budget-report-.*\.json$/.test(entry.name)) {
      matches.push(entryPath)
    }
  }
  return matches
}

async function readJson(filePath) {
  try {
    return JSON.parse(await readFile(filePath, 'utf8'))
  } catch (error) {
    throw new Error(`Invalid startup report JSON at ${filePath}: ${String(error)}`)
  }
}
