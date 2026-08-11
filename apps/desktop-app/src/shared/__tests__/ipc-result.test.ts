import { describe, expect, test } from 'vitest'
import { captureIpcResult } from '../ipc-result'

describe('ipc-result', () => {
  test('returns successful values without rejecting the main-process handler', async () => {
    const result = await captureIpcResult(async () => ({ models: ['model-a'] }))

    expect(result).toEqual({ ok: true, value: { models: ['model-a'] } })
  })

  test('serializes expected failures and restores their stable metadata in preload', async () => {
    const source = Object.assign(new Error('MODEL_DISCOVERY_UPSTREAM_ERROR: provider unavailable'), {
      name: 'LocalRuntimeModelRequestError',
      code: 'MODEL_DISCOVERY_UPSTREAM_ERROR',
      status: 502,
    })
    const result = await captureIpcResult(async () => {
      throw source
    })

    expect(result).toEqual({
      ok: false,
      error: {
        name: 'LocalRuntimeModelRequestError',
        message: 'MODEL_DISCOVERY_UPSTREAM_ERROR: provider unavailable',
        code: 'MODEL_DISCOVERY_UPSTREAM_ERROR',
        status: 502,
      },
    })
  })
})
