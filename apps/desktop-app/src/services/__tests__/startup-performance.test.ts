import { describe, expect, it } from 'vitest'

import {
  DEFAULT_DESKTOP_STARTUP_BUDGETS,
  DesktopStartupTracker,
  STARTUP_BUDGET_REPORT_PREFIX,
  formatDesktopStartupBudgetReport,
  readDesktopStartupBudgets,
} from '../startup-performance'

describe('Desktop startup performance', () => {
  it('measures actionable startup phases with a monotonic clock', () => {
    let now = 0
    const tracker = new DesktopStartupTracker({
      now: () => now,
      startedAtMs: 0,
      budgets: {
        process_to_app_ready_ms: 1_000,
        app_ready_to_services_ready_ms: 1_000,
        services_ready_to_renderer_loaded_ms: 2_000,
        total_ms: 4_000,
      },
    })

    now = 800
    tracker.mark('app_ready')
    now = 1_300
    tracker.mark('services_ready')
    now = 2_900
    tracker.mark('renderer_loaded')

    expect(tracker.report({ appVersion: '0.1.0', packaged: true })).toEqual({
      schema_version: 1,
      app_version: '0.1.0',
      platform: process.platform,
      arch: process.arch,
      packaged: true,
      timings_ms: {
        process_to_app_ready_ms: 800,
        app_ready_to_services_ready_ms: 500,
        services_ready_to_renderer_loaded_ms: 1_600,
        total_ms: 2_900,
      },
      budgets_ms: {
        process_to_app_ready_ms: 1_000,
        app_ready_to_services_ready_ms: 1_000,
        services_ready_to_renderer_loaded_ms: 2_000,
        total_ms: 4_000,
      },
      passed: true,
      violations: [],
    })
  })

  it('reports every exceeded phase without hiding a passing total', () => {
    let now = 0
    const tracker = new DesktopStartupTracker({
      now: () => now,
      startedAtMs: 0,
      budgets: {
        process_to_app_ready_ms: 500,
        app_ready_to_services_ready_ms: 300,
        services_ready_to_renderer_loaded_ms: 2_000,
        total_ms: 4_000,
      },
    })

    now = 700
    tracker.mark('app_ready')
    now = 1_100
    tracker.mark('services_ready')
    now = 2_500
    tracker.mark('renderer_loaded')

    const report = tracker.report({ appVersion: '0.1.0', packaged: false })

    expect(report.passed).toBe(false)
    expect(report.violations).toEqual([
      {
        phase: 'process_to_app_ready_ms',
        actual_ms: 700,
        budget_ms: 500,
      },
      {
        phase: 'app_ready_to_services_ready_ms',
        actual_ms: 400,
        budget_ms: 300,
      },
    ])
  })

  it('keeps optional startup diagnostics separate from budget calculations', () => {
    let now = 0
    const tracker = new DesktopStartupTracker({ now: () => now, startedAtMs: 0 })

    now = 100
    tracker.mark('app_ready')
    now = 200
    tracker.mark('services_ready')
    now = 240
    tracker.markDiagnostic('sidecar_spawned')
    now = 500
    tracker.markDiagnostic('sidecar_ready')
    now = 650
    tracker.markDiagnostic('desktop_session_installed')
    now = 700
    tracker.markDiagnostic('renderer_load_started')
    now = 1_200
    tracker.markDiagnostic('renderer_load_completed')
    now = 1_300
    tracker.mark('renderer_loaded')

    expect(tracker.report({ appVersion: '0.1.0', packaged: true })).toMatchObject({
      passed: true,
      diagnostics_ms: {
        sidecar_spawned_at_ms: 240,
        sidecar_ready_at_ms: 500,
        desktop_session_installed_at_ms: 650,
        renderer_load_started_at_ms: 700,
        renderer_load_completed_at_ms: 1_200,
        sidecar_startup_ms: 260,
        desktop_session_bootstrap_ms: 150,
        renderer_load_ms: 500,
      },
    })
  })

  it('does not let a repeated diagnostic milestone change its first timestamp', () => {
    let now = 0
    const tracker = new DesktopStartupTracker({ now: () => now, startedAtMs: 0 })

    now = 100
    tracker.markDiagnostic('sidecar_spawned')
    now = 900
    tracker.markDiagnostic('sidecar_spawned')
    now = 1_000
    tracker.mark('app_ready')
    tracker.mark('services_ready')
    tracker.mark('renderer_loaded')

    expect(tracker.report({ appVersion: '0.1.0', packaged: true }).diagnostics_ms).toMatchObject({
      sidecar_spawned_at_ms: 100,
    })
  })

  it('loads positive integer budget overrides and ignores malformed values', () => {
    const budgets = readDesktopStartupBudgets({
      HARNESS_DESKTOP_STARTUP_APP_READY_BUDGET_MS: '900',
      HARNESS_DESKTOP_STARTUP_SERVICES_BUDGET_MS: 'invalid',
      HARNESS_DESKTOP_STARTUP_RENDERER_BUDGET_MS: '-1',
      HARNESS_DESKTOP_STARTUP_TOTAL_BUDGET_MS: '6000',
    })

    expect(budgets).toEqual({
      ...DEFAULT_DESKTOP_STARTUP_BUDGETS,
      process_to_app_ready_ms: 900,
      total_ms: 6_000,
    })
  })

  it('rejects out-of-order milestones and incomplete reports', () => {
    const tracker = new DesktopStartupTracker({ now: () => 100, startedAtMs: 0 })

    expect(() => tracker.mark('services_ready')).toThrow('app_ready')
    tracker.mark('app_ready')
    tracker.mark('services_ready')
    expect(() => tracker.report({ appVersion: '0.1.0', packaged: false })).toThrow(
      'renderer_loaded',
    )
  })

  it('formats one machine-readable report line for the packaged smoke harness', () => {
    let now = 0
    const tracker = new DesktopStartupTracker({ now: () => now, startedAtMs: 0 })
    now = 100
    tracker.mark('app_ready')
    now = 200
    tracker.mark('services_ready')
    now = 300
    tracker.mark('renderer_loaded')

    const line = formatDesktopStartupBudgetReport(
      tracker.report({ appVersion: '0.1.0', packaged: true }),
    )

    expect(line.startsWith(STARTUP_BUDGET_REPORT_PREFIX)).toBe(true)
    expect(JSON.parse(line.slice(STARTUP_BUDGET_REPORT_PREFIX.length))).toMatchObject({
      schema_version: 1,
      passed: true,
      packaged: true,
    })
  })
})
