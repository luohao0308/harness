/**
 * Desktop telemetry tests
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  recordDesktopStartupTime,
  recordDesktopStartupReport,
  recordDesktopCrashEvent,
  submitDesktopFeedback,
  getDesktopTelemetryPayloadBase,
} from '../desktop-telemetry'
import * as apiClient from '../../shared/api-client'

vi.mock('electron', () => ({
  app: {
    getVersion: () => '0.1.0',
  },
}))

vi.mock('../../shared/api-client')

describe('Desktop Telemetry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    process.env.HARNESS_DESKTOP_UPDATE_CHANNEL = 'stable'
  })

  afterEach(() => {
    delete process.env.HARNESS_DESKTOP_UPDATE_CHANNEL
    delete process.env.DESKTOP_RELEASE_CHANNEL
  })

  describe('recordDesktopStartupTime', () => {
    it('should send startup time metric to API', async () => {
      vi.mocked(apiClient.apiRequest).mockResolvedValueOnce({})

      await recordDesktopStartupTime(1234)

      expect(apiClient.apiRequest).toHaveBeenCalledWith('/api/desktop/metrics', {
        method: 'POST',
        body: expect.stringContaining('startup_time_ms'),
      })
    })

    it('should include channel, version, and platform', async () => {
      vi.mocked(apiClient.apiRequest).mockResolvedValueOnce({})

      await recordDesktopStartupTime(1234)

      const callArg = vi.mocked(apiClient.apiRequest).mock.calls[0][1]
      const body = JSON.parse(callArg?.body as string)

      expect(body).toMatchObject({
        metric_name: 'startup_time_ms',
        channel: 'stable',
        app_version: '0.1.0',
        platform: process.platform,
        value: 1234,
      })
    })

    it('should attach the structured startup budget report to the compatible metric', async () => {
      vi.mocked(apiClient.apiRequest).mockResolvedValueOnce({})
      const report = {
        schema_version: 1 as const,
        app_version: '0.1.0',
        platform: process.platform,
        arch: process.arch,
        packaged: true,
        timings_ms: {
          process_to_app_ready_ms: 500,
          app_ready_to_services_ready_ms: 300,
          services_ready_to_renderer_loaded_ms: 1_200,
          total_ms: 2_000,
        },
        budgets_ms: {
          process_to_app_ready_ms: 2_000,
          app_ready_to_services_ready_ms: 1_500,
          services_ready_to_renderer_loaded_ms: 3_500,
          total_ms: 6_000,
        },
        passed: true,
        violations: [],
      }

      await recordDesktopStartupReport(report)

      const callArg = vi.mocked(apiClient.apiRequest).mock.calls[0][1]
      const body = JSON.parse(callArg?.body as string)
      expect(body).toMatchObject({
        metric_name: 'startup_time_ms',
        value: 2_000,
        metadata: {
          source: 'main-process',
          budget_passed: true,
          budget_violation_count: 0,
          startup_report: report,
        },
      })
    })
  })

  describe('recordDesktopCrashEvent', () => {
    it('should send crash event to API', async () => {
      vi.mocked(apiClient.apiRequest).mockResolvedValueOnce({})

      await recordDesktopCrashEvent('Test error')

      expect(apiClient.apiRequest).toHaveBeenCalledWith('/api/desktop/metrics', {
        method: 'POST',
        body: expect.stringContaining('crash_event'),
      })
    })

    it('should include error message in metadata', async () => {
      vi.mocked(apiClient.apiRequest).mockResolvedValueOnce({})

      await recordDesktopCrashEvent('Test error', { extra: 'data' })

      const callArg = vi.mocked(apiClient.apiRequest).mock.calls[0][1]
      const body = JSON.parse(callArg?.body as string)

      expect(body.metadata).toMatchObject({
        error: 'Test error',
        extra: 'data',
      })
    })
  })

  describe('submitDesktopFeedback', () => {
    it('should submit feedback to API', async () => {
      vi.mocked(apiClient.apiRequest).mockResolvedValueOnce({ success: true })

      const result = await submitDesktopFeedback({
        title: 'Test Feedback',
        description: 'This is a test',
        category: 'bug',
      })

      expect(apiClient.apiRequest).toHaveBeenCalledWith('/api/desktop/feedback', {
        method: 'POST',
        body: expect.stringContaining('Test Feedback'),
      })
      expect(result).toEqual({ success: true })
    })

    it('should include optional fields when provided', async () => {
      vi.mocked(apiClient.apiRequest).mockResolvedValueOnce({})

      await submitDesktopFeedback({
        title: 'Test',
        description: 'Desc',
        logs: ['log1', 'log2'],
        screenshot_data_url: 'data:image/png;base64,ABC',
        metadata: { extra: 'info' },
      })

      const callArg = vi.mocked(apiClient.apiRequest).mock.calls[0][1]
      const body = JSON.parse(callArg?.body as string)

      expect(body).toMatchObject({
        title: 'Test',
        description: 'Desc',
        logs: ['log1', 'log2'],
        screenshot_data_url: 'data:image/png;base64,ABC',
        metadata: { extra: 'info' },
      })
    })
  })

  describe('getDesktopTelemetryPayloadBase', () => {
    it('should return base payload with stable channel', () => {
      const payload = getDesktopTelemetryPayloadBase()

      expect(payload).toEqual({
        channel: 'stable',
        app_version: '0.1.0',
        platform: process.platform,
      })
    })

    it('should return beta channel when env is set', () => {
      process.env.HARNESS_DESKTOP_UPDATE_CHANNEL = 'beta'

      const payload = getDesktopTelemetryPayloadBase()

      expect(payload.channel).toBe('beta')
    })

    it('should fallback to DESKTOP_RELEASE_CHANNEL', () => {
      delete process.env.HARNESS_DESKTOP_UPDATE_CHANNEL
      process.env.DESKTOP_RELEASE_CHANNEL = 'beta'

      const payload = getDesktopTelemetryPayloadBase()

      expect(payload.channel).toBe('beta')
    })
  })
})
