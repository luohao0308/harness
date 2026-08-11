import { BrowserWindow, dialog, ipcMain } from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import type {
  DesktopFileChangeEvent,
  DesktopFileEntry,
  DesktopFileListResult,
  DesktopFileReadResult,
  DesktopFileWatchState,
  DesktopFileWriteResult,
} from '../preload-api'

type WindowProvider = () => BrowserWindow | null

type WatchHandle = {
  watcher: fs.FSWatcher
}

const MAX_READ_BYTES = 512 * 1024
const MAX_WRITE_BYTES = 1024 * 1024
const MAX_LIST_ENTRIES = 500
const MAX_LIST_DEPTH = 8

const windowState = new WeakMap<BrowserWindow, DesktopFileWatchState>()
const windowWatchers = new WeakMap<BrowserWindow, WatchHandle>()
const lifecycleBoundWindows = new WeakSet<BrowserWindow>()
let fileHandlersRegistered = false

export function registerFileHandlers(): void {
  if (fileHandlersRegistered) return
  fileHandlersRegistered = true

  ipcMain.handle('file:select-workspace-root', async (event): Promise<DesktopFileWatchState | null> => {
    const window = BrowserWindow.fromWebContents(event.sender)
    if (!window) return null
    bindWindowLifecycle(window)
    const result = await dialog.showOpenDialog(window, {
      title: '选择工作区目录',
      properties: ['openDirectory', 'createDirectory'],
    })
    if (result.canceled || result.filePaths.length === 0) return null
    return setWindowWorkspaceRoot(window, result.filePaths[0] ?? null)
  })

  ipcMain.handle('file:get-workspace-root', (event): DesktopFileWatchState => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    return getWindowState(window)
  })

  ipcMain.handle('file:set-workspace-root', (event, rootPath: string | null): DesktopFileWatchState => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    return setWindowWorkspaceRoot(window, rootPath)
  })

  ipcMain.handle('file:start-watch', (event): DesktopFileWatchState => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    return startWatchForWindow(window)
  })

  ipcMain.handle('file:stop-watch', (event): DesktopFileWatchState => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    return stopWatchForWindow(window)
  })

  ipcMain.handle(
    'file:list-files',
    (event, options?: { path?: string; maxDepth?: number; maxEntries?: number }): DesktopFileListResult => {
      const window = BrowserWindow.fromWebContents(event.sender)
      bindWindowLifecycle(window)
      const state = getWindowState(window)
      if (!state.rootPath) {
        return { rootPath: null, entries: [], truncated: false }
      }
      return listFiles(state.rootPath, options)
    },
  )

  ipcMain.handle('file:read-file', (event, filePath: string): DesktopFileReadResult => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    const state = getWindowState(window)
    if (!state.rootPath) {
      throw new Error('workspace root is not configured')
    }
    return readFile(state.rootPath, filePath)
  })

  ipcMain.handle('file:write-file', (event, filePath: string, content: string): DesktopFileWriteResult => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    const state = getWindowState(window)
    if (!state.rootPath) {
      throw new Error('workspace root is not configured')
    }
    return writeFile(state.rootPath, filePath, content)
  })
}

function bindWindowLifecycle(window: BrowserWindow | null): void {
  if (!window || lifecycleBoundWindows.has(window)) return
  lifecycleBoundWindows.add(window)
  window.once('closed', () => {
    const watcher = windowWatchers.get(window)
    if (watcher) {
      watcher.watcher.close()
      windowWatchers.delete(window)
    }
    windowState.delete(window)
    lifecycleBoundWindows.delete(window)
  })
}

function getWindowState(window: BrowserWindow | null): DesktopFileWatchState {
  if (!window) return { rootPath: null, watching: false }
  return windowState.get(window) ?? { rootPath: null, watching: false }
}

function setWindowWorkspaceRoot(window: BrowserWindow | null, rootPath: string | null): DesktopFileWatchState {
  if (!window) return { rootPath: null, watching: false }
  const normalized = rootPath?.trim() || null
  if (normalized === null) {
    stopWatchForWindow(window)
    windowState.set(window, { rootPath: null, watching: false })
    return { rootPath: null, watching: false }
  }
  const resolved = path.resolve(normalized)
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
    throw new Error('workspace root must be an existing directory')
  }
  const next = { rootPath: resolved, watching: false }
  windowState.set(window, next)
  return startWatchForWindow(window)
}

function startWatchForWindow(window: BrowserWindow | null): DesktopFileWatchState {
  if (!window) return { rootPath: null, watching: false }
  const state = getWindowState(window)
  if (!state.rootPath) return state
  stopWatchForWindow(window)
  const watcher = fs.watch(state.rootPath, { recursive: false }, (eventType, filename) => {
    if (!filename) return
    let changedPath: string
    try {
      changedPath = resolveLexicalWithinRoot(state.rootPath!, filename.toString())
    } catch {
      return
    }
    const payload: DesktopFileChangeEvent = {
      rootPath: state.rootPath!,
      path: changedPath,
      eventType: eventType === 'rename' ? 'rename' : 'change',
      kind: inferKind(state.rootPath!, filename.toString()),
      changedAt: new Date().toISOString(),
    }
    window.webContents.send('file:change', payload)
  })
  windowWatchers.set(window, { watcher })
  const next = { rootPath: state.rootPath, watching: true }
  windowState.set(window, next)
  return next
}

function stopWatchForWindow(window: BrowserWindow | null): DesktopFileWatchState {
  if (!window) return { rootPath: null, watching: false }
  const existing = windowWatchers.get(window)
  if (existing) {
    existing.watcher.close()
    windowWatchers.delete(window)
  }
  const state = getWindowState(window)
  const next = { rootPath: state.rootPath, watching: false }
  windowState.set(window, next)
  return next
}

function readFile(rootPath: string, rawPath: string): DesktopFileReadResult {
  const { targetPath: filePath, relativePath } = resolveExistingWithinRoot(rootPath, rawPath)
  const stat = fs.lstatSync(filePath)
  if (!stat.isFile()) {
    throw new Error('path is not a file')
  }
  const raw = fs.readFileSync(filePath)
  const clipped = raw.subarray(0, MAX_READ_BYTES)
  const sizeBytes = clipped.byteLength
  const content = clipped.toString('utf-8')
  const mimeType = guessMimeType(filePath) ?? 'application/octet-stream'
  return {
    path: relativePath || '.',
    content,
    sizeBytes,
    totalSizeBytes: stat.size,
    mimeType,
    truncated: stat.size > MAX_READ_BYTES,
    editable: isEditableTextFile(filePath),
  }
}

function writeFile(rootPath: string, rawPath: string, content: string): DesktopFileWriteResult {
  const { targetPath: filePath, relativePath } = resolveWritableWithinRoot(rootPath, rawPath)
  const raw = Buffer.from(content, 'utf-8')
  if (raw.byteLength > MAX_WRITE_BYTES) {
    throw new Error(`file content exceeds ${MAX_WRITE_BYTES} bytes`)
  }
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  const tempPath = path.join(path.dirname(filePath), `.${path.basename(filePath)}.${makeTempSuffix()}.tmp`)
  try {
    fs.writeFileSync(tempPath, raw, { mode: 0o600 })
    fs.renameSync(tempPath, filePath)
  } catch (error) {
    if (fs.existsSync(tempPath)) {
      fs.unlinkSync(tempPath)
    }
    throw error
  }
  return {
    path: relativePath || '.',
    bytesWritten: raw.byteLength,
    updatedAt: new Date().toISOString(),
  }
}

function listFiles(
  rootPath: string,
  options?: { path?: string; maxDepth?: number; maxEntries?: number },
): DesktopFileListResult {
  const relPath = options?.path?.trim() || '.'
  const maxDepth = clampInt(options?.maxDepth, 1, MAX_LIST_DEPTH)
  const maxEntries = clampInt(options?.maxEntries, 1, MAX_LIST_ENTRIES)
  const { rootPath: resolvedRootPath, targetPath: start } = resolveExistingWithinRoot(rootPath, relPath)
  const entries: DesktopFileEntry[] = []
  walkDirectory(resolvedRootPath, start, 0, maxDepth, maxEntries, entries)
  return {
    rootPath: resolvedRootPath,
    entries,
    truncated: entries.length >= maxEntries,
  }
}

function walkDirectory(
  rootPath: string,
  currentPath: string,
  depth: number,
  maxDepth: number,
  maxEntries: number,
  entries: DesktopFileEntry[],
): void {
  const stat = fs.lstatSync(currentPath)
  if (stat.isSymbolicLink()) {
    throwPathNotAllowed(rootPath, path.relative(rootPath, currentPath))
  }
  const kind = stat.isDirectory() ? 'directory' : 'file'
  entries.push({
    path: path.relative(rootPath, currentPath) || '.',
    name: path.basename(currentPath),
    kind,
    sizeBytes: stat.isFile() ? stat.size : 0,
    modifiedAt: stat.mtime.toISOString(),
    depth,
    mimeType: stat.isFile() ? guessMimeType(currentPath) : null,
  })
  if (entries.length >= maxEntries) return
  if (!stat.isDirectory() || depth >= maxDepth) return
  for (const entry of fs.readdirSync(currentPath).sort((a, b) => a.localeCompare(b))) {
    if (entries.length >= maxEntries) return
    walkDirectory(rootPath, path.join(currentPath, entry), depth + 1, maxDepth, maxEntries, entries)
  }
}

function resolveWithinRoot(rootPath: string, rawPath: string): string {
  return resolveExistingWithinRoot(rootPath, rawPath).targetPath
}

function resolveLexicalWithinRoot(rootPath: string, rawPath: string): string {
  const normalizedRoot = path.resolve(rootPath)
  const candidate = path.resolve(normalizedRoot, rawPath)
  assertInsideRoot(normalizedRoot, candidate, rawPath)
  return candidate
}

function resolveExistingWithinRoot(
  rootPath: string,
  rawPath: string,
): { rootPath: string; targetPath: string; relativePath: string } {
  const normalizedRoot = path.resolve(rootPath)
  const rootRealPath = fs.realpathSync(normalizedRoot)
  const candidate = path.resolve(normalizedRoot, rawPath)
  assertInsideRoot(normalizedRoot, candidate, rawPath)
  assertExistingPathHasNoSymlink(normalizedRoot, rootRealPath, candidate, rawPath)
  return {
    rootPath: normalizedRoot,
    targetPath: candidate,
    relativePath: toRelative(normalizedRoot, candidate),
  }
}

function resolveWritableWithinRoot(
  rootPath: string,
  rawPath: string,
): { rootPath: string; targetPath: string; relativePath: string } {
  const normalizedRoot = path.resolve(rootPath)
  const rootRealPath = fs.realpathSync(normalizedRoot)
  const candidate = path.resolve(normalizedRoot, rawPath)
  assertInsideRoot(normalizedRoot, candidate, rawPath)
  assertWritablePathHasNoSymlink(normalizedRoot, rootRealPath, candidate, rawPath)
  return {
    rootPath: normalizedRoot,
    targetPath: candidate,
    relativePath: toRelative(normalizedRoot, candidate),
  }
}

function assertInsideRoot(rootPath: string, candidate: string, rawPath: string): void {
  const relative = path.relative(rootPath, candidate)
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    throwPathNotAllowed(rootPath, rawPath)
  }
}

function assertExistingPathHasNoSymlink(
  rootPath: string,
  rootRealPath: string,
  targetPath: string,
  rawPath: string,
): void {
  assertPathSegmentsHaveNoSymlink(rootPath, targetPath, rawPath, true)
  assertRealPathInsideRoot(rootRealPath, targetPath, rawPath)
}

function assertWritablePathHasNoSymlink(
  rootPath: string,
  rootRealPath: string,
  targetPath: string,
  rawPath: string,
): void {
  assertPathSegmentsHaveNoSymlink(rootPath, path.dirname(targetPath), rawPath, false)
  if (!fs.existsSync(targetPath)) return
  const stat = fs.lstatSync(targetPath)
  if (stat.isSymbolicLink()) {
    throwPathNotAllowed(rootPath, rawPath)
  }
  if (stat.isDirectory()) {
    throw new Error(`path is not writable: ${sanitizeRelativePathForError(rawPath)}`)
  }
  assertRealPathInsideRoot(rootRealPath, targetPath, rawPath)
}

function assertPathSegmentsHaveNoSymlink(
  rootPath: string,
  targetPath: string,
  rawPath: string,
  requireTarget: boolean,
): void {
  const relative = path.relative(rootPath, targetPath)
  if (!relative) return
  let currentPath = rootPath
  for (const segment of relative.split(path.sep).filter(Boolean)) {
    currentPath = path.join(currentPath, segment)
    if (!fs.existsSync(currentPath)) {
      if (requireTarget) {
        throwPathNotAllowed(rootPath, rawPath)
      }
      return
    }
    const stat = fs.lstatSync(currentPath)
    if (stat.isSymbolicLink()) {
      throwPathNotAllowed(rootPath, rawPath)
    }
    if (!stat.isDirectory() && currentPath !== targetPath) {
      throw new Error(`path parent is not a directory: ${sanitizeRelativePathForError(rawPath)}`)
    }
  }
}

function assertRealPathInsideRoot(rootRealPath: string, targetPath: string, rawPath: string): void {
  const targetRealPath = fs.realpathSync(targetPath)
  const relative = path.relative(rootRealPath, targetRealPath)
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    throwPathNotAllowed(rootRealPath, rawPath)
  }
}

function throwPathNotAllowed(_rootRealPath: string, rawPath: string): never {
  throw new Error(`path is not allowed: ${sanitizeRelativePathForError(rawPath)}`)
}

function sanitizeRelativePathForError(rawPath: string): string {
  const trimmed = rawPath.trim() || '.'
  if (path.isAbsolute(trimmed)) {
    return path.basename(trimmed) || '.'
  }
  return path.normalize(trimmed).replaceAll(path.sep, '/')
}

function toRelative(rootRealPath: string, targetPath: string): string {
  return path.relative(rootRealPath, targetPath).replaceAll(path.sep, '/')
}

function makeTempSuffix(): string {
  return `${Date.now().toString(36)}-${process.pid}-${Math.random().toString(36).slice(2)}`
}

function inferKind(rootPath: string, rawPath: string): 'file' | 'directory' | 'unknown' {
  try {
    const filePath = resolveWithinRoot(rootPath, rawPath)
    const stat = fs.existsSync(filePath) ? fs.statSync(filePath) : null
    if (stat === null) return 'unknown'
    return stat.isDirectory() ? 'directory' : 'file'
  } catch {
    return 'unknown'
  }
}

function guessMimeType(filePath: string): string | null {
  const lower = filePath.toLowerCase()
  if (lower.endsWith('.md') || lower.endsWith('.txt') || lower.endsWith('.log')) return 'text/plain'
  if (lower.endsWith('.json')) return 'application/json'
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'application/yaml'
  if (lower.endsWith('.ts')) return 'text/typescript'
  if (lower.endsWith('.tsx')) return 'text/x-typescript'
  if (lower.endsWith('.js')) return 'text/javascript'
  if (lower.endsWith('.jsx')) return 'text/jsx'
  return null
}

function isEditableTextFile(filePath: string): boolean {
  const mimeType = guessMimeType(filePath)
  return mimeType !== null || /\.(txt|md|markdown|json|jsonl|yaml|yml|log|ini|env|ts|tsx|js|jsx|css|html|xml)$/i.test(filePath)
}

function clampInt(value: number | undefined, min: number, max: number): number {
  const parsed = Number.isFinite(value ?? NaN) ? Math.trunc(value as number) : min
  return Math.max(min, Math.min(max, parsed))
}
