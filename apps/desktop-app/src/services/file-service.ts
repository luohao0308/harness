import { BrowserWindow, dialog, ipcMain } from 'electron'
import { createHash } from 'node:crypto'
import * as fs from 'fs'
import * as path from 'path'
import { TextDecoder } from 'node:util'
import type {
  DesktopFileChangeEvent,
  DesktopFileEntry,
  DesktopFileListResult,
  DesktopProjectKnowledgeScanOptions,
  DesktopProjectKnowledgeSnapshot,
  DesktopProjectKnowledgeSnapshotFile,
  DesktopFileReadResult,
  DesktopFileWatchState,
  DesktopFileWriteResult,
  DesktopWorkspaceAuthorization,
} from '../preload-api'
import {
  getActiveProfile,
  getActiveProfileWorkspaceRoot,
  setActiveProfileWorkspaceRoot,
} from './phase6-store'
import * as phase6Store from './phase6-store'

type WindowProvider = () => BrowserWindow | null

type WatchHandle = {
  watcher: fs.FSWatcher
}

type InternalFileState = DesktopFileWatchState & {
  profileId: string
}

const MAX_READ_BYTES = 512 * 1024
const MAX_WRITE_BYTES = 1024 * 1024
const MAX_LIST_ENTRIES = 500
const MAX_LIST_DEPTH = 8
const PROJECT_SCAN_DEFAULT_MAX_FILES = 1_000
const PROJECT_SCAN_MAX_FILES = 5_000
const PROJECT_SCAN_DEFAULT_MAX_FILE_BYTES = 120_000
const PROJECT_SCAN_MAX_FILE_BYTES = 120_000
const PROJECT_SCAN_DEFAULT_MAX_TOTAL_BYTES = 4 * 1024 * 1024
const PROJECT_SCAN_MAX_TOTAL_BYTES = 16 * 1024 * 1024
const PROJECT_SCAN_DEFAULT_MAX_DURATION_MS = 5_000
const PROJECT_SCAN_MAX_DURATION_MS = 15_000
const PROJECT_SCAN_MAX_IGNORE_PATTERNS = 64
const PROJECT_SCAN_DEFAULT_IGNORE_VERSION = 'v1'

const PROJECT_SCAN_IGNORED_DIRECTORIES = new Set([
  '.git',
  '.hg',
  '.svn',
  '.cache',
  '.mypy_cache',
  '.next',
  '.nuxt',
  '.parcel-cache',
  '.pytest_cache',
  '.ruff_cache',
  '.tox',
  '.turbo',
  '.venv',
  '__pycache__',
  'build',
  'coverage',
  'dist',
  'env',
  'node_modules',
  'out',
  'target',
  'venv',
  'vendor',
])

const PROJECT_SCAN_SUPPORTED_EXTENSIONS = new Set([
  '.adoc', '.bash', '.c', '.cc', '.cfg', '.conf', '.cpp', '.cs', '.css', '.csv',
  '.fish', '.go', '.gql', '.graphql', '.h', '.hpp', '.htm', '.html', '.ini', '.java',
  '.js', '.json', '.jsonl', '.jsx', '.kt', '.kts', '.less', '.md', '.markdown', '.mjs',
  '.php', '.properties', '.proto', '.ps1', '.py', '.pyi', '.rb', '.rs', '.rst', '.scss',
  '.sh', '.sql', '.svelte', '.swift', '.toml', '.ts', '.tsv', '.tsx', '.txt', '.vue',
  '.xml', '.yaml', '.yml', '.zsh',
])

const PROJECT_SCAN_SUPPORTED_FILENAMES = new Set([
  '.gitignore',
  'containerfile',
  'dockerfile',
  'gemfile',
  'justfile',
  'makefile',
  'procfile',
  'rakefile',
])

const PROJECT_SCAN_SECRET_FILENAMES = new Set([
  '.netrc',
  '.npmrc',
  '.pypirc',
  'credentials',
  'credentials.json',
  'id_dsa',
  'id_ed25519',
  'id_rsa',
  'secrets.json',
])

const PROJECT_SCAN_SECRET_EXTENSIONS = new Set(['.key', '.p12', '.pfx', '.pem'])

const windowState = new WeakMap<BrowserWindow, InternalFileState>()
const windowWatchers = new WeakMap<BrowserWindow, WatchHandle>()
const lifecycleBoundWindows = new WeakSet<BrowserWindow>()
let fileHandlersRegistered = false

export function registerFileHandlers(options: {
  authorizeWorkspace?: (
    profileId: string,
    rootPath: string,
  ) => Promise<DesktopWorkspaceAuthorization>
} = {}): void {
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

  ipcMain.handle(
    'file:select-authorized-workspace-root',
    async (event): Promise<DesktopWorkspaceAuthorization | null> => {
      const window = BrowserWindow.fromWebContents(event.sender)
      if (!window) return null
      const result = await dialog.showOpenDialog(window, {
        title: '选择自动化工作区目录',
        properties: ['openDirectory'],
      })
      if (result.canceled || result.filePaths.length === 0) return null
      if (!options.authorizeWorkspace) {
        throw new Error('workspace authorization is unavailable')
      }
      const rootPath = validateWorkspaceRoot(result.filePaths[0] ?? '')
      return options.authorizeWorkspace(getActiveProfile().id, rootPath)
    },
  )

  ipcMain.handle('file:get-workspace-root', (event): DesktopFileWatchState => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    return getWindowWorkspaceState(window)
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
      const state = getWindowWorkspaceState(window)
      if (!state.rootPath) {
        return { rootPath: null, entries: [], truncated: false }
      }
      return listFiles(state.rootPath, options)
    },
  )

  ipcMain.handle(
    'file:scan-project-knowledge',
    async (event, options?: DesktopProjectKnowledgeScanOptions): Promise<DesktopProjectKnowledgeSnapshot> => {
      const window = BrowserWindow.fromWebContents(event.sender)
      bindWindowLifecycle(window)
      const state = getWindowWorkspaceState(window)
      if (!state.rootPath) {
        throw new Error('workspace root is not configured')
      }
      return scanProjectKnowledge(state.rootPath, options)
    },
  )

  ipcMain.handle('file:read-file', (event, filePath: string): DesktopFileReadResult => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    const state = getWindowWorkspaceState(window)
    if (!state.rootPath) {
      throw new Error('workspace root is not configured')
    }
    return readFile(state.rootPath, filePath)
  })

  ipcMain.handle('file:write-file', (event, filePath: string, content: string): DesktopFileWriteResult => {
    const window = BrowserWindow.fromWebContents(event.sender)
    bindWindowLifecycle(window)
    const state = getWindowWorkspaceState(window)
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

export function getWindowWorkspaceState(window: BrowserWindow | null): DesktopFileWatchState {
  if (!window) return { rootPath: null, watching: false }
  const state = getInternalWindowState(window)
  return { rootPath: state.rootPath, watching: state.watching }
}

function setWindowWorkspaceRoot(window: BrowserWindow | null, rootPath: string | null): DesktopFileWatchState {
  if (!window) return { rootPath: null, watching: false }
  closeWindowWatcher(window)
  const profileId = getActiveProfile().id
  const normalized = rootPath?.trim() || null
  if (normalized === null) {
    setActiveProfileWorkspaceRoot(null)
    windowState.set(window, { profileId, rootPath: null, watching: false })
    return { rootPath: null, watching: false }
  }
  const resolved = validateWorkspaceRoot(normalized)
  setActiveProfileWorkspaceRoot(resolved)
  const next: InternalFileState = { profileId, rootPath: resolved, watching: false }
  windowState.set(window, next)
  return startWatchForWindow(window)
}

function startWatchForWindow(window: BrowserWindow | null): DesktopFileWatchState {
  if (!window) return { rootPath: null, watching: false }
  const state = getInternalWindowState(window)
  if (!state.rootPath) return { rootPath: null, watching: false }
  closeWindowWatcher(window)
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
  const next: InternalFileState = { ...state, watching: true }
  windowState.set(window, next)
  return { rootPath: next.rootPath, watching: next.watching }
}

function stopWatchForWindow(window: BrowserWindow | null): DesktopFileWatchState {
  if (!window) return { rootPath: null, watching: false }
  const state = getInternalWindowState(window)
  closeWindowWatcher(window)
  const next: InternalFileState = { ...state, watching: false }
  windowState.set(window, next)
  return { rootPath: next.rootPath, watching: next.watching }
}

function getInternalWindowState(window: BrowserWindow): InternalFileState {
  const profileId = getActiveProfile().id
  const existing = windowState.get(window)
  if (existing?.profileId === profileId) return existing
  closeWindowWatcher(window)
  const storedRoot = getActiveProfileWorkspaceRoot()
  let rootPath: string | null = null
  if (storedRoot) {
    try {
      rootPath = validateWorkspaceRoot(storedRoot)
    } catch {
      setActiveProfileWorkspaceRoot(null)
    }
  }
  const next: InternalFileState = { profileId, rootPath, watching: false }
  windowState.set(window, next)
  return next
}

function closeWindowWatcher(window: BrowserWindow): void {
  const existing = windowWatchers.get(window)
  if (!existing) return
  existing.watcher.close()
  windowWatchers.delete(window)
}

function validateWorkspaceRoot(rootPath: string): string {
  const resolved = path.resolve(rootPath)
  if (!fs.existsSync(resolved)) {
    throw new Error('workspace root must be an existing directory')
  }
  const stat = fs.lstatSync(resolved)
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error('workspace root must be a non-symlink directory')
  }
  return fs.realpathSync(resolved)
}

export async function scanProjectKnowledge(
  rootPath: string,
  options: DesktopProjectKnowledgeScanOptions = {},
): Promise<DesktopProjectKnowledgeSnapshot> {
  const resolvedRoot = validateWorkspaceRoot(rootPath)
  const rootStat = fs.lstatSync(resolvedRoot)
  const startedAtMs = Date.now()
  const startedAt = new Date(startedAtMs).toISOString()
  const limits = normalizeProjectScanOptions(options)
  const ignorePatterns = normalizeProjectIgnorePatterns(options.ignorePatterns)
  const files: DesktopProjectKnowledgeSnapshotFile[] = []
  const errors: Array<{ path: string; reason: string }> = []
  let scannedFiles = 0
  let indexedFiles = 0
  let totalBytes = 0
  let truncationReason: DesktopProjectKnowledgeSnapshot['truncationReason'] = null

  const markIncomplete = (
    reason: Exclude<DesktopProjectKnowledgeSnapshot['truncationReason'], null>,
  ): void => {
    truncationReason ??= reason
  }

  const visitDirectory = async (directoryPath: string, relativeDirectory: string): Promise<void> => {
    if (truncationReason || Date.now() - startedAtMs >= limits.maxDurationMs) {
      markIncomplete('max_duration')
      return
    }
    let entries: fs.Dirent[]
    try {
      entries = await fs.promises.readdir(directoryPath, { withFileTypes: true })
    } catch {
      errors.push({ path: relativeDirectory || '.', reason: 'directory_read_failed' })
      markIncomplete('scan_error')
      return
    }
    entries.sort((left, right) => left.name.localeCompare(right.name))
    for (const entry of entries) {
      if (truncationReason || Date.now() - startedAtMs >= limits.maxDurationMs) {
        markIncomplete('max_duration')
        return
      }
      const relativePath = normalizeProjectRelativePath(
        relativeDirectory ? `${relativeDirectory}/${entry.name}` : entry.name,
      )
      const targetPath = path.join(directoryPath, entry.name)
      let stat: fs.Stats
      try {
        stat = await fs.promises.lstat(targetPath)
      } catch {
        errors.push({ path: relativePath, reason: 'stat_failed' })
        markIncomplete('scan_error')
        continue
      }
      if (stat.isSymbolicLink()) {
        scannedFiles += 1
        if (scannedFiles > limits.maxFiles) {
          markIncomplete('max_files')
          return
        }
        files.push(skippedProjectFile(relativePath, stat, 'symlink'))
        continue
      }
      if (stat.isDirectory()) {
        if (
          isDefaultIgnoredProjectDirectory(entry.name)
          || matchesProjectIgnore(relativePath, true, ignorePatterns)
        ) {
          continue
        }
        await visitDirectory(targetPath, relativePath)
        continue
      }
      if (!stat.isFile()) continue
      if (isDefaultIgnoredProjectFile(relativePath)) continue
      if (matchesProjectIgnore(relativePath, false, ignorePatterns)) continue
      if (!isSupportedProjectKnowledgeFile(relativePath)) continue
      scannedFiles += 1
      if (scannedFiles > limits.maxFiles) {
        markIncomplete('max_files')
        return
      }
      if (stat.size > limits.maxFileBytes) {
        files.push(skippedProjectFile(relativePath, stat, 'file_too_large'))
        continue
      }
      if (totalBytes + stat.size > limits.maxTotalBytes) {
        markIncomplete('max_total_bytes')
        return
      }
      try {
        const safePath = resolveExistingWithinRoot(resolvedRoot, relativePath).targetPath
        const contentBytes = await fs.promises.readFile(safePath)
        const verifiedStat = await fs.promises.lstat(safePath)
        if (
          verifiedStat.isSymbolicLink()
          || verifiedStat.size !== stat.size
          || verifiedStat.mtimeMs !== stat.mtimeMs
        ) {
          files.push(skippedProjectFile(relativePath, verifiedStat, 'changed_during_scan'))
          markIncomplete('scan_error')
          continue
        }
        let content: string
        try {
          content = new TextDecoder('utf-8', { fatal: true }).decode(contentBytes)
        } catch {
          files.push(skippedProjectFile(relativePath, stat, 'invalid_utf8'))
          continue
        }
        totalBytes += contentBytes.byteLength
        indexedFiles += 1
        files.push({
          relativePath,
          status: 'ready',
          content,
          contentSha256: createHash('sha256').update(contentBytes).digest('hex'),
          sizeBytes: contentBytes.byteLength,
          modifiedAt: verifiedStat.mtime.toISOString(),
          mimeType: guessMimeType(relativePath) ?? 'text/plain',
          skipReason: null,
        })
      } catch {
        files.push(skippedProjectFile(relativePath, stat, 'read_failed'))
        errors.push({ path: relativePath, reason: 'file_read_failed' })
        markIncomplete('scan_error')
      }
    }
  }

  await visitDirectory(resolvedRoot, '')
  files.sort((left, right) => left.relativePath.localeCompare(right.relativePath))
  const completedAt = new Date().toISOString()
  const rootIdentity = createHash('sha256')
    .update(`${resolvedRoot}\0${rootStat.dev}\0${rootStat.ino}`)
    .digest('hex')
  const snapshotGeneration = phase6Store.nextProjectKnowledgeSnapshotGeneration?.(rootIdentity) ?? 1
  const cursorEnvelope = {
    schema_version: 'desktop-project-knowledge-cursor-v2',
    snapshot_schema_version: 'desktop-project-knowledge-snapshot-v2',
    default_ignore_version: PROJECT_SCAN_DEFAULT_IGNORE_VERSION,
    root_identity: rootIdentity,
    ignore_patterns: ignorePatterns,
    limits,
    complete: truncationReason === null,
    truncated: truncationReason !== null,
    truncation_reason: truncationReason,
    errors,
    stats: { scanned_files: scannedFiles, indexed_files: indexedFiles, total_bytes: totalBytes },
    files: files.map((file) => [
      file.relativePath, file.status, file.contentSha256, file.sizeBytes,
      file.modifiedAt, file.mimeType, file.skipReason,
    ]),
  }
  const snapshotCursor = createHash('sha256')
    .update(JSON.stringify(cursorEnvelope))
    .digest('hex')
  return {
    schemaVersion: 'desktop-project-knowledge-snapshot-v2',
    defaultIgnoreVersion: PROJECT_SCAN_DEFAULT_IGNORE_VERSION,
    rootIdentity,
    snapshotGeneration,
    snapshotCursor,
    complete: truncationReason === null,
    truncated: truncationReason !== null,
    truncationReason,
    files,
    errors,
    scannedFiles,
    indexedFiles,
    totalBytes,
    startedAt,
    completedAt,
  }
}

function normalizeProjectScanOptions(options: DesktopProjectKnowledgeScanOptions): {
  maxFiles: number
  maxFileBytes: number
  maxTotalBytes: number
  maxDurationMs: number
} {
  return {
    maxFiles: clampOptionalInt(
      options.maxFiles,
      1,
      PROJECT_SCAN_MAX_FILES,
      PROJECT_SCAN_DEFAULT_MAX_FILES,
    ),
    maxFileBytes: clampOptionalInt(
      options.maxFileBytes,
      1,
      PROJECT_SCAN_MAX_FILE_BYTES,
      PROJECT_SCAN_DEFAULT_MAX_FILE_BYTES,
    ),
    maxTotalBytes: clampOptionalInt(
      options.maxTotalBytes,
      1,
      PROJECT_SCAN_MAX_TOTAL_BYTES,
      PROJECT_SCAN_DEFAULT_MAX_TOTAL_BYTES,
    ),
    maxDurationMs: clampOptionalInt(
      options.maxDurationMs,
      1,
      PROJECT_SCAN_MAX_DURATION_MS,
      PROJECT_SCAN_DEFAULT_MAX_DURATION_MS,
    ),
  }
}

function normalizeProjectIgnorePatterns(value: string[] | undefined): string[] {
  if (value === undefined) return []
  if (!Array.isArray(value) || value.length > PROJECT_SCAN_MAX_IGNORE_PATTERNS) {
    throw new Error(`ignore patterns cannot exceed ${PROJECT_SCAN_MAX_IGNORE_PATTERNS}`)
  }
  const normalized: string[] = []
  for (const rawPattern of value) {
    if (typeof rawPattern !== 'string') throw new Error('ignore patterns must be strings')
    const pattern = rawPattern.trim().replaceAll('\\', '/').replace(/^\.\//, '')
    if (!pattern || pattern.length > 240 || pattern.startsWith('/')) {
      throw new Error('ignore patterns must be relative and contain 1 to 240 characters')
    }
    if (pattern.split('/').includes('..') || pattern.includes('\0')) {
      throw new Error('ignore patterns cannot traverse parents')
    }
    if (!normalized.includes(pattern)) normalized.push(pattern)
  }
  return normalized
}

function matchesProjectIgnore(relativePath: string, directory: boolean, patterns: string[]): boolean {
  return patterns.some((pattern) => {
    const normalizedPattern = pattern.replace(/\/+$/, '')
    const expression = projectGlobToRegExp(normalizedPattern)
    if (expression.test(relativePath)) return true
    return directory && expression.test(`${relativePath}/`)
  })
}

function projectGlobToRegExp(pattern: string): RegExp {
  let expression = ''
  for (let index = 0; index < pattern.length; index += 1) {
    const character = pattern[index]
    if (character === '*') {
      if (pattern[index + 1] === '*') {
        expression += '.*'
        index += 1
      } else {
        expression += '[^/]*'
      }
    } else if (character === '?') {
      expression += '[^/]'
    } else {
      expression += character?.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') ?? ''
    }
  }
  return pattern.includes('/')
    ? new RegExp(`^${expression}(?:/.*)?$`)
    : new RegExp(`(?:^|/)${expression}(?:$|/)`)
}

function isDefaultIgnoredProjectDirectory(name: string): boolean {
  return PROJECT_SCAN_IGNORED_DIRECTORIES.has(name.toLowerCase())
}

function isDefaultIgnoredProjectFile(relativePath: string): boolean {
  const baseName = path.posix.basename(relativePath).toLowerCase()
  if (baseName === '.env' || baseName.startsWith('.env.')) return true
  if (PROJECT_SCAN_SECRET_FILENAMES.has(baseName)) return true
  if (PROJECT_SCAN_SECRET_EXTENSIONS.has(path.posix.extname(baseName))) return true
  return baseName.startsWith('secrets.') || baseName.startsWith('credentials.')
}

function isSupportedProjectKnowledgeFile(relativePath: string): boolean {
  const baseName = path.posix.basename(relativePath).toLowerCase()
  return (
    PROJECT_SCAN_SUPPORTED_FILENAMES.has(baseName)
    || PROJECT_SCAN_SUPPORTED_EXTENSIONS.has(path.posix.extname(baseName))
  )
}

function skippedProjectFile(
  relativePath: string,
  stat: fs.Stats,
  reason: DesktopProjectKnowledgeSnapshotFile['skipReason'],
): DesktopProjectKnowledgeSnapshotFile {
  return {
    relativePath,
    status: 'skipped',
    content: null,
    contentSha256: null,
    sizeBytes: stat.size,
    modifiedAt: stat.mtime.toISOString(),
    mimeType: guessMimeType(relativePath),
    skipReason: reason,
  }
}

function normalizeProjectRelativePath(value: string): string {
  return value.split(path.sep).join('/').replace(/^\.\//, '')
}

function clampOptionalInt(
  value: number | undefined,
  min: number,
  max: number,
  fallback: number,
): number {
  if (!Number.isFinite(value)) return fallback
  return Math.max(min, Math.min(max, Math.trunc(value as number)))
}

export function readFile(rootPath: string, rawPath: string): DesktopFileReadResult {
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

export function writeFile(rootPath: string, rawPath: string, content: string): DesktopFileWriteResult {
  return writeFileWithBaseline(rootPath, rawPath, content)
}

export type DesktopFileBaseline = {
  path: string
  exists: boolean
  sha256: string | null
  mtimeMs: number | null
  sizeBytes: number | null
}

export function getFileBaseline(rootPath: string, rawPath: string): DesktopFileBaseline {
  const { targetPath: filePath, relativePath } = resolveWritableWithinRoot(rootPath, rawPath)
  if (!fs.existsSync(filePath)) {
    return { path: relativePath || '.', exists: false, sha256: null, mtimeMs: null, sizeBytes: null }
  }
  const stat = fs.lstatSync(filePath)
  if (!stat.isFile()) throw new Error('path is not a file')
  return {
    path: relativePath || '.', exists: true,
    sha256: createHash('sha256').update(fs.readFileSync(filePath)).digest('hex'),
    mtimeMs: stat.mtimeMs, sizeBytes: stat.size,
  }
}

export function writeFileWithBaseline(
  rootPath: string,
  rawPath: string,
  content: string,
  expected?: DesktopFileBaseline | null,
): DesktopFileWriteResult {
  const { targetPath: filePath, relativePath } = resolveWritableWithinRoot(rootPath, rawPath)
  if (expected) {
    const current = getFileBaseline(rootPath, rawPath)
    if (current.exists !== expected.exists || current.sha256 !== expected.sha256
      || current.mtimeMs !== expected.mtimeMs || current.sizeBytes !== expected.sizeBytes) {
      throw new Error(`workspace file changed since approval: ${relativePath || '.'}`)
    }
  }
  const raw = Buffer.from(content, 'utf-8')
  if (raw.byteLength > MAX_WRITE_BYTES) {
    throw new Error(`file content exceeds ${MAX_WRITE_BYTES} bytes`)
  }
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  if (expected?.exists) {
    throw new Error(
      `workspace file changed since approval: ${relativePath || '.'} (existing-file compare-and-swap is unavailable)`,
    )
  }
  const lockPath = path.join(path.dirname(filePath), `.${path.basename(filePath)}.harness-approval.lock`)
  let lockFd: number | null = null
  if (expected) {
    try {
      lockFd = fs.openSync(lockPath, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY, 0o600)
    } catch {
      throw new Error(`workspace file is already being approved: ${relativePath || '.'}`)
    }
  }
  const tempPath = path.join(path.dirname(filePath), `.${path.basename(filePath)}.${makeTempSuffix()}.tmp`)
  try {
    if (expected && !expected.exists) {
      // link() is atomic and refuses to replace a file created after approval.
      fs.writeFileSync(tempPath, raw, { mode: 0o600 })
      fs.linkSync(tempPath, filePath)
      fs.unlinkSync(tempPath)
    } else {
      fs.writeFileSync(tempPath, raw, { mode: 0o600 })
      fs.renameSync(tempPath, filePath)
    }
  } catch (error) {
    if (fs.existsSync(tempPath)) {
      fs.unlinkSync(tempPath)
    }
    throw error
  } finally {
    if (lockFd !== null) {
      fs.closeSync(lockFd)
      if (fs.existsSync(lockPath)) fs.unlinkSync(lockPath)
    }
  }
  return {
    path: relativePath || '.',
    bytesWritten: raw.byteLength,
    updatedAt: new Date().toISOString(),
  }
}

export function listFiles(
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
