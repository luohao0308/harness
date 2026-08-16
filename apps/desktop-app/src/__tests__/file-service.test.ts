import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

type MockWatcher = {
  close: ReturnType<typeof vi.fn>
}

describe('file bridge', () => {
  let mockIpcMain: {
    handle: ReturnType<typeof vi.fn>
  }
  let mockDialog: {
    showOpenDialog: ReturnType<typeof vi.fn>
  }
  let mockWindow: {
    once: ReturnType<typeof vi.fn>
    webContents: {
      send: ReturnType<typeof vi.fn>
    }
  }
  let currentWindow: typeof mockWindow | null
  let watchMock: ReturnType<typeof vi.fn>
  let watcherCloseMock: ReturnType<typeof vi.fn>
  let writeFileSyncMock: ReturnType<typeof vi.fn>
  let renameSyncMock: ReturnType<typeof vi.fn>
  let watchCallback:
    | ((eventType: string, filename: Buffer | string | null) => void)
    | undefined

  beforeEach(() => {
    vi.resetModules()
    watchCallback = undefined
    watcherCloseMock = vi.fn()
    mockWindow = {
      once: vi.fn(),
      webContents: {
        send: vi.fn(),
      },
    }
    currentWindow = mockWindow
    mockIpcMain = {
      handle: vi.fn(),
    }
    mockDialog = {
      showOpenDialog: vi.fn(),
    }

    vi.doMock('electron', () => ({
      BrowserWindow: {
        fromWebContents: vi.fn(() => currentWindow as never),
      },
      dialog: mockDialog,
      ipcMain: mockIpcMain,
    }))

    vi.doMock('fs', async () => {
      const actual = await vi.importActual<typeof import('fs')>('fs')
      writeFileSyncMock = vi.fn((...args: Parameters<typeof actual.writeFileSync>) => actual.writeFileSync(...args))
      renameSyncMock = vi.fn((...args: Parameters<typeof actual.renameSync>) => actual.renameSync(...args))
      return {
        ...actual,
        renameSync: renameSyncMock,
        watch: vi.fn((...args: unknown[]) => {
          watchCallback = args[args.length - 1] as typeof watchCallback
          return { close: watcherCloseMock } as MockWatcher
        }),
        writeFileSync: writeFileSyncMock,
      }
    })

  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  function createWorkspace(): string {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-file-bridge-'))
    fs.mkdirSync(path.join(root, 'nested'))
    fs.writeFileSync(path.join(root, 'binary.bin'), Buffer.from([0, 1, 2, 3]))
    fs.writeFileSync(path.join(root, 'notes.txt'), 'hello world')
    fs.writeFileSync(path.join(root, 'nested', 'child.md'), '# child')
    return root
  }

  async function registerHandlers() {
    const { registerFileHandlers } = await import('../services/file-service')
    registerFileHandlers()
    return {
      select: mockIpcMain.handle.mock.calls.find((call) => call[0] === 'file:select-workspace-root')?.[1],
      get: mockIpcMain.handle.mock.calls.find((call) => call[0] === 'file:get-workspace-root')?.[1],
      set: mockIpcMain.handle.mock.calls.find((call) => call[0] === 'file:set-workspace-root')?.[1],
      start: mockIpcMain.handle.mock.calls.find((call) => call[0] === 'file:start-watch')?.[1],
      stop: mockIpcMain.handle.mock.calls.find((call) => call[0] === 'file:stop-watch')?.[1],
      list: mockIpcMain.handle.mock.calls.find((call) => call[0] === 'file:list-files')?.[1],
      read: mockIpcMain.handle.mock.calls.find((call) => call[0] === 'file:read-file')?.[1],
      write: mockIpcMain.handle.mock.calls.find((call) => call[0] === 'file:write-file')?.[1],
    }
  }

  test('selects workspace roots and stops watching on window close', async () => {
    const workspaceRoot = createWorkspace()
    mockDialog.showOpenDialog.mockResolvedValue({
      canceled: false,
      filePaths: [workspaceRoot],
    })

    const handlers = await registerHandlers()
    const selected = await handlers.select?.({ sender: { id: 'sender' } } as never)

    expect(selected).toEqual({ rootPath: workspaceRoot, watching: true })
    expect(mockDialog.showOpenDialog).toHaveBeenCalledWith(
      mockWindow,
      expect.objectContaining({
        properties: ['openDirectory', 'createDirectory'],
      })
    )
    expect(mockWindow.once).toHaveBeenCalledWith('closed', expect.any(Function))
    expect(mockIpcMain.handle).toHaveBeenCalledWith('file:select-workspace-root', expect.any(Function))

    const closedHandler = mockWindow.once.mock.calls.find((call) => call[0] === 'closed')?.[1]
    closedHandler?.()

    expect(handlers.get?.({ sender: { id: 'sender' } } as never)).toEqual({
      rootPath: null,
      watching: false,
    })
  })

  test('lists, reads, writes, and reports file changes within the workspace root', async () => {
    const workspaceRoot = createWorkspace()
    const handlers = await registerHandlers()

    expect(handlers.set).toBeDefined()
    expect(handlers.list).toBeDefined()
    expect(handlers.read).toBeDefined()
    expect(handlers.write).toBeDefined()
    expect(handlers.start).toBeDefined()
    expect(handlers.stop).toBeDefined()

    expect(await handlers.set!({ sender: { id: 'sender' } } as never, workspaceRoot)).toEqual({
      rootPath: workspaceRoot,
      watching: true,
    })

    const list = await handlers.list!({ sender: { id: 'sender' } } as never, { maxDepth: 2, maxEntries: 10 })
    expect(list).toMatchObject({
      rootPath: workspaceRoot,
      truncated: false,
    })
    expect(list?.entries.map((entry: { path: string }) => entry.path)).toEqual([
      '.',
      'binary.bin',
      'nested',
      'nested/child.md',
      'notes.txt',
    ])

    const read = await handlers.read!({ sender: { id: 'sender' } } as never, 'notes.txt')
    expect(read).toMatchObject({
      path: 'notes.txt',
      content: 'hello world',
      sizeBytes: 11,
      totalSizeBytes: 11,
      mimeType: 'text/plain',
      truncated: false,
      editable: true,
    })

    const binaryRead = await handlers.read!({ sender: { id: 'sender' } } as never, 'binary.bin')
    expect(binaryRead).toMatchObject({
      mimeType: 'application/octet-stream',
      editable: false,
    })

    const write = await handlers.write!({ sender: { id: 'sender' } } as never, 'nested/new.txt', 'saved')
    expect(write).toMatchObject({
      path: 'nested/new.txt',
      bytesWritten: 5,
    })
    expect(fs.readFileSync(path.join(workspaceRoot, 'nested', 'new.txt'), 'utf-8')).toBe('saved')

    await handlers.start!({ sender: { id: 'sender' } } as never)

    const { watch } = await import('fs')
    expect(vi.mocked(watch)).toHaveBeenCalledWith(
      workspaceRoot,
      expect.objectContaining({ recursive: false }),
      expect.any(Function)
    )
    expect(watchCallback).toBeDefined()
    watchCallback?.('rename', 'nested/new.txt')

    expect(mockWindow.webContents.send).toHaveBeenCalledWith(
      'file:change',
      expect.objectContaining({
        rootPath: workspaceRoot,
        path: path.join(workspaceRoot, 'nested', 'new.txt'),
        eventType: 'rename',
        kind: 'file',
      })
    )

    expect(await handlers.stop!({ sender: { id: 'sender' } } as never)).toEqual({
      rootPath: workspaceRoot,
      watching: false,
    })
  })

  test('rejects workspace roots outside the filesystem', async () => {
    const handlers = await registerHandlers()
    expect(handlers.set).toBeDefined()
    await expect(
      Promise.resolve().then(() =>
        handlers.set!({ sender: { id: 'sender' } } as never, path.join(os.tmpdir(), 'no-such-workspace-root'))
      )
    ).rejects.toThrow('workspace root must be an existing directory')
  })

  test('rejects symlink escapes on read, list, and write with sanitized relative errors', async () => {
    const workspaceRoot = createWorkspace()
    const outsideRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-file-outside-'))
    const outsideFile = path.join(outsideRoot, 'secret.txt')
    fs.writeFileSync(outsideFile, 'secret')
    fs.symlinkSync(outsideFile, path.join(workspaceRoot, 'secret-link.txt'))
    fs.symlinkSync(outsideRoot, path.join(workspaceRoot, 'outside-link'))

    const handlers = await registerHandlers()
    await handlers.set!({ sender: { id: 'sender' } } as never, workspaceRoot)

    expect(() => handlers.read!({ sender: { id: 'sender' } } as never, 'secret-link.txt')).toThrow(
      'path is not allowed: secret-link.txt'
    )
    expect(() => handlers.list!({ sender: { id: 'sender' } } as never, { path: 'outside-link' })).toThrow(
      'path is not allowed: outside-link'
    )
    expect(() => handlers.write!({ sender: { id: 'sender' } } as never, 'outside-link/written.txt', 'blocked')).toThrow(
      'path is not allowed: outside-link/written.txt'
    )
    expect(() => handlers.write!({ sender: { id: 'sender' } } as never, 'secret-link.txt', 'blocked')).toThrow(
      'path is not allowed: secret-link.txt'
    )

    for (const getError of [
      () => handlers.read!({ sender: { id: 'sender' } } as never, 'secret-link.txt'),
      () => handlers.list!({ sender: { id: 'sender' } } as never, { path: 'outside-link' }),
      () => handlers.write!({ sender: { id: 'sender' } } as never, 'outside-link/written.txt', 'blocked'),
    ]) {
      let error: Error | null = null
      try {
        getError()
      } catch (caught) {
        error = caught as Error
      }
      if (!(error instanceof Error)) {
        throw new Error('expected file operation to throw')
      }
      expect(error.message).not.toContain(workspaceRoot)
      expect(error.message).not.toContain(outsideRoot)
    }
  })

  test('writes through an atomic temp file, renames into place, and rejects oversized content', async () => {
    const workspaceRoot = createWorkspace()
    const handlers = await registerHandlers()
    await handlers.set!({ sender: { id: 'sender' } } as never, workspaceRoot)

    const write = await handlers.write!({ sender: { id: 'sender' } } as never, 'nested/atomic.txt', 'atomic')

    expect(write).toMatchObject({
      path: 'nested/atomic.txt',
      bytesWritten: 6,
    })
    expect(writeFileSyncMock).toHaveBeenCalledWith(
      expect.stringMatching(/\.atomic\.txt\.[^.]+\.tmp$/),
      Buffer.from('atomic', 'utf-8'),
      expect.objectContaining({ mode: 0o600 })
    )
    expect(renameSyncMock).toHaveBeenCalledWith(
      expect.stringMatching(/\.atomic\.txt\.[^.]+\.tmp$/),
      path.join(workspaceRoot, 'nested', 'atomic.txt')
    )
    expect(fs.readFileSync(path.join(workspaceRoot, 'nested', 'atomic.txt'), 'utf-8')).toBe('atomic')

    const oversized = 'x'.repeat(1024 * 1024 + 1)
    expect(() => handlers.write!({ sender: { id: 'sender' } } as never, 'nested/too-large.txt', oversized)).toThrow(
      'file content exceeds 1048576 bytes'
    )
    expect(fs.existsSync(path.join(workspaceRoot, 'nested', 'too-large.txt'))).toBe(false)
  })

  test('closes the previous watcher when restarting and on window close', async () => {
    const workspaceRoot = createWorkspace()
    const handlers = await registerHandlers()

    await handlers.set!({ sender: { id: 'sender' } } as never, workspaceRoot)
    expect(await handlers.start!({ sender: { id: 'sender' } } as never)).toEqual({
      rootPath: workspaceRoot,
      watching: true,
    })
    expect(watcherCloseMock).toHaveBeenCalledTimes(1)

    const closedHandler = mockWindow.once.mock.calls.find((call) => call[0] === 'closed')?.[1]
    closedHandler?.()

    expect(watcherCloseMock).toHaveBeenCalledTimes(2)
    expect(handlers.get?.({ sender: { id: 'sender' } } as never)).toEqual({
      rootPath: null,
      watching: false,
    })
  })
})
