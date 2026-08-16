import { performance } from 'node:perf_hooks'

export const STARTUP_BUDGET_REPORT_PREFIX = 'HARNESS_DESKTOP_STARTUP_REPORT '

export type DesktopStartupMilestone = 'app_ready' | 'services_ready' | 'renderer_loaded'

export type DesktopStartupDiagnosticMilestone =
  | 'sidecar_spawned'
  | 'sidecar_ready'
  | 'desktop_session_installed'
  | 'renderer_load_started'
  | 'renderer_load_completed'

export type DesktopStartupDiagnostics = {
  sidecar_spawned_at_ms?: number
  sidecar_ready_at_ms?: number
  desktop_session_installed_at_ms?: number
  renderer_load_started_at_ms?: number
  renderer_load_completed_at_ms?: number
  sidecar_startup_ms?: number
  desktop_session_bootstrap_ms?: number
  renderer_load_ms?: number
}

export type DesktopStartupTimings = {
  process_to_app_ready_ms: number
  app_ready_to_services_ready_ms: number
  services_ready_to_renderer_loaded_ms: number
  total_ms: number
}

export type DesktopStartupBudgets = DesktopStartupTimings

export type DesktopStartupBudgetViolation = {
  phase: keyof DesktopStartupTimings
  actual_ms: number
  budget_ms: number
}

export type DesktopStartupReport = {
  schema_version: 1
  app_version: string
  platform: NodeJS.Platform
  arch: string
  packaged: boolean
  timings_ms: DesktopStartupTimings
  budgets_ms: DesktopStartupBudgets
  passed: boolean
  violations: DesktopStartupBudgetViolation[]
  diagnostics_ms?: DesktopStartupDiagnostics
}

export const DEFAULT_DESKTOP_STARTUP_BUDGETS: DesktopStartupBudgets = Object.freeze({
  process_to_app_ready_ms: 2_000,
  app_ready_to_services_ready_ms: 1_500,
  services_ready_to_renderer_loaded_ms: 3_500,
  total_ms: 6_000,
})

const BUDGET_ENV_KEYS: Record<keyof DesktopStartupBudgets, string> = {
  process_to_app_ready_ms: 'HARNESS_DESKTOP_STARTUP_APP_READY_BUDGET_MS',
  app_ready_to_services_ready_ms: 'HARNESS_DESKTOP_STARTUP_SERVICES_BUDGET_MS',
  services_ready_to_renderer_loaded_ms: 'HARNESS_DESKTOP_STARTUP_RENDERER_BUDGET_MS',
  total_ms: 'HARNESS_DESKTOP_STARTUP_TOTAL_BUDGET_MS',
}

type StartupTrackerOptions = {
  now?: () => number
  startedAtMs?: number
  budgets?: DesktopStartupBudgets
}

export class DesktopStartupTracker {
  private readonly now: () => number
  private readonly startedAtMs: number
  private readonly budgets: DesktopStartupBudgets
  private readonly milestones: Partial<Record<DesktopStartupMilestone, number>> = {}
  private readonly diagnosticMilestones: Partial<Record<DesktopStartupDiagnosticMilestone, number>> = {}

  constructor(options: StartupTrackerOptions = {}) {
    this.now = options.now ?? (() => performance.now())
    this.startedAtMs = options.startedAtMs ?? 0
    this.budgets = options.budgets ?? readDesktopStartupBudgets()
  }

  mark(milestone: DesktopStartupMilestone): void {
    const previous = previousMilestone(milestone)
    if (previous && this.milestones[previous] === undefined) {
      throw new Error(`desktop startup milestone ${previous} must be recorded first`)
    }
    if (this.milestones[milestone] !== undefined) {
      throw new Error(`desktop startup milestone ${milestone} was already recorded`)
    }
    this.milestones[milestone] = this.now()
  }

  markDiagnostic(milestone: DesktopStartupDiagnosticMilestone): void {
    if (this.diagnosticMilestones[milestone] !== undefined) return
    this.diagnosticMilestones[milestone] = this.now()
  }

  report(input: { appVersion: string; packaged: boolean }): DesktopStartupReport {
    const appReadyAt = this.requiredMilestone('app_ready')
    const servicesReadyAt = this.requiredMilestone('services_ready')
    const rendererLoadedAt = this.requiredMilestone('renderer_loaded')
    const timings: DesktopStartupTimings = {
      process_to_app_ready_ms: duration(this.startedAtMs, appReadyAt),
      app_ready_to_services_ready_ms: duration(appReadyAt, servicesReadyAt),
      services_ready_to_renderer_loaded_ms: duration(servicesReadyAt, rendererLoadedAt),
      total_ms: duration(this.startedAtMs, rendererLoadedAt),
    }
    const violations = (Object.keys(timings) as Array<keyof DesktopStartupTimings>)
      .filter((phase) => timings[phase] > this.budgets[phase])
      .map((phase) => ({
        phase,
        actual_ms: timings[phase],
        budget_ms: this.budgets[phase],
      }))

    const diagnostics = buildDiagnostics(this.diagnosticMilestones)
    return {
      schema_version: 1,
      app_version: input.appVersion,
      platform: process.platform,
      arch: process.arch,
      packaged: input.packaged,
      timings_ms: timings,
      budgets_ms: { ...this.budgets },
      passed: violations.length === 0,
      violations,
      ...(diagnostics ? { diagnostics_ms: diagnostics } : {}),
    }
  }

  private requiredMilestone(milestone: DesktopStartupMilestone): number {
    const value = this.milestones[milestone]
    if (value === undefined) {
      throw new Error(`desktop startup milestone ${milestone} has not been recorded`)
    }
    return value
  }
}

function buildDiagnostics(
  milestones: Partial<Record<DesktopStartupDiagnosticMilestone, number>>,
): DesktopStartupDiagnostics | undefined {
  const values = Object.fromEntries(Object.entries(milestones).map(([milestone, timestamp]) => [
    `${milestone}_at_ms`, Math.max(0, Math.round(timestamp as number)),
  ])) as DesktopStartupDiagnostics
  const duration = (start: DesktopStartupDiagnosticMilestone, end: DesktopStartupDiagnosticMilestone) => {
    const startedAt = milestones[start]
    const finishedAt = milestones[end]
    return startedAt === undefined || finishedAt === undefined
      ? undefined
      : Math.max(0, Math.round(finishedAt - startedAt))
  }
  const durations: DesktopStartupDiagnostics = {
    sidecar_startup_ms: duration('sidecar_spawned', 'sidecar_ready'),
    desktop_session_bootstrap_ms: duration('sidecar_ready', 'desktop_session_installed'),
    renderer_load_ms: duration('renderer_load_started', 'renderer_load_completed'),
  }
  const diagnostics = { ...values, ...Object.fromEntries(
    Object.entries(durations).filter(([, value]) => value !== undefined),
  ) } as DesktopStartupDiagnostics
  return Object.keys(diagnostics).length > 0 ? diagnostics : undefined
}

export function readDesktopStartupBudgets(
  env: Record<string, string | undefined> = process.env,
): DesktopStartupBudgets {
  return (Object.keys(BUDGET_ENV_KEYS) as Array<keyof DesktopStartupBudgets>).reduce(
    (budgets, phase) => ({
      ...budgets,
      [phase]: positiveInteger(env[BUDGET_ENV_KEYS[phase]]) ?? DEFAULT_DESKTOP_STARTUP_BUDGETS[phase],
    }),
    { ...DEFAULT_DESKTOP_STARTUP_BUDGETS },
  )
}

export function isDesktopStartupBudgetMode(
  argv: readonly string[] = process.argv,
  env: Record<string, string | undefined> = process.env,
): boolean {
  return argv.includes('--startup-budget-smoke') || env.HARNESS_DESKTOP_STARTUP_BUDGET_MODE === '1'
}

export function formatDesktopStartupBudgetReport(report: DesktopStartupReport): string {
  return `${STARTUP_BUDGET_REPORT_PREFIX}${JSON.stringify(report)}`
}

function previousMilestone(milestone: DesktopStartupMilestone): DesktopStartupMilestone | null {
  if (milestone === 'services_ready') return 'app_ready'
  if (milestone === 'renderer_loaded') return 'services_ready'
  return null
}

function duration(startedAtMs: number, finishedAtMs: number): number {
  return Math.max(0, Math.round(finishedAtMs - startedAtMs))
}

function positiveInteger(value: string | undefined): number | null {
  if (!value || !/^\d+$/.test(value)) return null
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}
