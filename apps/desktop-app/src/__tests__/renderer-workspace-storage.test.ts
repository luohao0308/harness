import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'

const mocks = vi.hoisted(() => ({
  userDataPath: '',
  profileId: 'default',
  on: vi.fn(),
}))

vi.mock('electron', () => ({
  app: { getPath: vi.fn(() => mocks.userDataPath) },
  ipcMain: { on: mocks.on },
}))

vi.mock('../services/phase6-store', () => ({
  getActiveProfile: () => ({ id: mocks.profileId }),
}))

import {
  readWorkspaceValue,
  removeWorkspaceValue,
  writeWorkspaceValue,
} from '../services/renderer-workspace-storage'

describe('renderer workspace storage', () => {
  beforeEach(() => {
    mocks.userDataPath = fs.mkdtempSync(path.join(os.tmpdir(), 'renderer-workspace-state-'))
    mocks.profileId = 'default'
  })

  afterEach(() => {
    fs.rmSync(mocks.userDataPath, { recursive: true, force: true })
  })

  test('persists workspace values across reads and isolates profiles', () => {
    const key = 'harness.workspace.desktop.v1.registry'
    expect(writeWorkspaceValue(key, '{"root":"/workspace"}')).toBe(true)
    expect(readWorkspaceValue(key)).toBe('{"root":"/workspace"}')

    mocks.profileId = 'other-profile'
    expect(readWorkspaceValue(key)).toBeNull()
    expect(writeWorkspaceValue(key, 'other')).toBe(true)

    mocks.profileId = 'default'
    expect(readWorkspaceValue(key)).toBe('{"root":"/workspace"}')
    expect(removeWorkspaceValue(key)).toBe(true)
    expect(readWorkspaceValue(key)).toBeNull()
  })

  test('rejects non-workspace keys and oversized values', () => {
    expect(writeWorkspaceValue('harness.auth.access_token', 'secret')).toBe(false)
    expect(readWorkspaceValue('harness.auth.access_token')).toBeNull()
    expect(writeWorkspaceValue('harness.workspace.desktop.large', 'x'.repeat(8 * 1024 * 1024 + 1))).toBe(false)
  })
})
