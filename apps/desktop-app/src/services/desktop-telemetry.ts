import { app } from 'electron'
import { apiRequest } from '../shared/api-client'
import type { DesktopStartupReport } from './startup-performance'

export type DesktopTelemetryMetricName = 'startup_time_ms' | 'crash_event' | 'sync_success' | 'sync_failure'

export type DesktopTelemetryClient = {
  recordMetric: (payload: {
    metric_name: DesktopTelemetryMetricName
    channel?: 'stable' | 'beta'
    app_version: string
    platform: string
    value?: number
    metadata?: Record<string, unknown>
  }) => Promise<unknown>
  submitFeedback: (payload: {
    title: string
    description: string
    category?: 'bug' | 'idea' | 'praise' | 'support'
    channel?: 'stable' | 'beta'
    app_version: string
    platform: string
    logs?: string[]
    screenshot_data_url?: string | null
    metadata?: Record<string, unknown>
  }) => Promise<unknown>
}

function getDesktopVersion(): string {
  return typeof app.getVersion === 'function' ? app.getVersion() : process.env.npm_package_version || '0.1.0'
}

function getDesktopChannel(): 'stable' | 'beta' {
  return (process.env.HARNESS_DESKTOP_UPDATE_CHANNEL || process.env.DESKTOP_RELEASE_CHANNEL || 'stable').toLowerCase() === 'beta'
    ? 'beta'
    : 'stable'
}

function getPlatform(): string {
  return process.platform
}

export async function recordDesktopStartupTime(
  startupTimeMs: number,
  metadata: Record<string, unknown> = {},
): Promise<void> {
  await apiRequest('/api/desktop/metrics', {
    method: 'POST',
    body: JSON.stringify({
      metric_name: 'startup_time_ms',
      channel: getDesktopChannel(),
      app_version: getDesktopVersion(),
      platform: getPlatform(),
      value: startupTimeMs,
      metadata: { source: 'main-process', ...metadata },
    }),
  })
}

export async function recordDesktopStartupReport(report: DesktopStartupReport): Promise<void> {
  await recordDesktopStartupTime(report.timings_ms.total_ms, {
    startup_report: report,
    budget_passed: report.passed,
    budget_violation_count: report.violations.length,
  })
}

export async function recordDesktopCrashEvent(error: string, metadata: Record<string, unknown> = {}): Promise<void> {
  await apiRequest('/api/desktop/metrics', {
    method: 'POST',
    body: JSON.stringify({
      metric_name: 'crash_event',
      channel: getDesktopChannel(),
      app_version: getDesktopVersion(),
      platform: getPlatform(),
      value: 1,
      metadata: { error, ...metadata },
    }),
  })
}

export async function submitDesktopFeedback(payload: {
  title: string
  description: string
  category?: 'bug' | 'idea' | 'praise' | 'support'
  logs?: string[]
  screenshot_data_url?: string | null
  metadata?: Record<string, unknown>
}): Promise<unknown> {
  return apiRequest('/api/desktop/feedback', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      channel: getDesktopChannel(),
      app_version: getDesktopVersion(),
      platform: getPlatform(),
    }),
  })
}

export function getDesktopTelemetryPayloadBase(): { channel: 'stable' | 'beta'; app_version: string; platform: string } {
  return {
    channel: getDesktopChannel(),
    app_version: getDesktopVersion(),
    platform: getPlatform(),
  }
}
