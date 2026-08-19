import { createHash, randomUUID } from 'node:crypto'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { spawn } from 'node:child_process'

import { apiRequest } from '../shared/api-client'
import type {
  DesktopChangeDiff,
  DesktopChangeDiffHunk,
  DesktopChangeDiffKind,
  DesktopChangeDiffMode,
  DesktopChangeDiffSection,
  DesktopChangeFile,
  DesktopChangeMutationInput,
  DesktopChangeMutationResult,
  DesktopChangeReviewAction,
  DesktopChangeReviewAuditContext,
  DesktopChangeReviewState,
  DesktopChangeReviewStatus,
} from '../preload-api'

export type {
  DesktopChangeDiff,
  DesktopChangeDiffHunk,
  DesktopChangeDiffSection,
  DesktopChangeFile,
  DesktopChangeMutationInput,
  DesktopChangeMutationResult,
  DesktopChangeReviewAction,
  DesktopChangeReviewAuditContext,
  DesktopChangeReviewStatus,
} from '../preload-api'

export type ChangeReviewAuditPhase = 'requested' | 'completed' | 'failed'

export type ChangeReviewAuditRecord = {
  operationId: string
  phase: ChangeReviewAuditPhase
  action: DesktopChangeReviewAction
  path: string
  hunkIds: string[]
  previewSha256: string
  auditContext?: DesktopChangeReviewAuditContext
  errorCode?: string
}

export type ChangeReviewAuditReceipt = {
  accepted: boolean
  auditId: string
  eventId: string | null
  operationId: string
  phase: ChangeReviewAuditPhase
}

export type ChangeReviewAuditRecorder = (
  record: ChangeReviewAuditRecord,
) => Promise<ChangeReviewAuditReceipt>

export type GitCommandOptions = {
  input?: string
  allowedExitCodes?: number[]
  timeoutMs?: number
  maxOutputBytes?: number
}

export type GitCommandResult = {
  stdout: string
  stderr: string
  exitCode: number
}

export type GitCommandRunner = (
  rootPath: string,
  args: string[],
  options?: GitCommandOptions,
) => Promise<GitCommandResult>

type InternalHunk = DesktopChangeDiffHunk & {
  raw: string
}

type InternalSection = DesktopChangeDiffSection & {
  fullPatch: string
  patchSha256: string
  headerText: string
  internalHunks: InternalHunk[]
}

type PreviewSnapshot = {
  owner: unknown
  rootPath: string
  path: string
  expiresAtMs: number
  previewSha256: string
  untracked: boolean
  sections: InternalSection[]
}

type ChangeReviewServiceOptions = {
  gitRunner?: GitCommandRunner
  auditRecorder?: ChangeReviewAuditRecorder
  now?: () => number
  tokenFactory?: () => string
  previewTtlMs?: number
}

type BranchStatus = {
  branch: string | null
  upstream: string | null
  ahead: number
  behind: number
}

const DEFAULT_GIT_TIMEOUT_MS = 8_000
const DEFAULT_GIT_OUTPUT_BYTES = 2 * 1024 * 1024
const DEFAULT_PREVIEW_TTL_MS = 5 * 60 * 1_000
const MAX_PREVIEWS = 200
const MAX_HUNKS_PER_MUTATION = 200
const COMPLETED_AUDIT_RECONCILIATION_ATTEMPTS = 3
const BINARY_SNIFF_BYTES = 8 * 1024
const CONFLICT_CODES = new Set(['DD', 'AU', 'UD', 'UA', 'DU', 'AA', 'UU'])

export class ChangeReviewError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'ChangeReviewError'
    this.code = code
  }
}

export class ChangeReviewService {
  private readonly gitRunner: GitCommandRunner
  private readonly auditRecorder: ChangeReviewAuditRecorder
  private readonly now: () => number
  private readonly tokenFactory: () => string
  private readonly previewTtlMs: number
  private readonly previews = new Map<string, PreviewSnapshot>()

  constructor(options: ChangeReviewServiceOptions = {}) {
    this.gitRunner = options.gitRunner ?? runGitCommand
    this.auditRecorder = options.auditRecorder ?? recordChangeReviewAudit
    this.now = options.now ?? Date.now
    this.tokenFactory = options.tokenFactory ?? randomUUID
    this.previewTtlMs = options.previewTtlMs ?? DEFAULT_PREVIEW_TTL_MS
  }

  async getStatus(rawRootPath: string | null): Promise<DesktopChangeReviewStatus> {
    if (!rawRootPath) return emptyStatus('no-workspace', null)
    let rootPath: string
    try {
      rootPath = validateWorkspaceRoot(rawRootPath)
      const repository = await this.resolveRepository(rootPath)
      if (repository.state !== 'ready') return repository
      const result = await this.gitRunner(rootPath, [
        'status',
        '--porcelain=v1',
        '-z',
        '--branch',
        '--untracked-files=all',
      ])
      const parsed = parseStatusOutput(result.stdout)
      return {
        state: 'ready',
        rootPath,
        repositoryRoot: rootPath,
        ...parsed.branch,
        files: parsed.files,
        errorCode: null,
        message: null,
      }
    } catch (error) {
      return degradedStatus(rawRootPath, error)
    }
  }

  async getDiff(rawRootPath: string | null, rawPath: string, owner: unknown): Promise<DesktopChangeDiff> {
    const rootPath = requireWorkspaceRoot(rawRootPath)
    const repository = await this.requireRepository(rootPath)
    const relativePath = validateWorkspacePath(repository, rawPath)
    const status = await this.requireReadyStatus(repository)
    const file = status.files.find((item) => item.path === relativePath)
    if (!file) {
      throw new ChangeReviewError('CHANGE_NOT_FOUND', `change not found: ${sanitizePath(rawPath)}`)
    }
    const sections = await this.readDiffSections(repository, file)
    const token = this.tokenFactory()
    const expiresAtMs = this.now() + this.previewTtlMs
    const previewSha256 = sha256(sections.map((section) => section.patchSha256).join(':'))
    this.prunePreviews()
    this.previews.set(token, {
      owner,
      rootPath: repository,
      path: relativePath,
      expiresAtMs,
      previewSha256,
      untracked: file.untracked,
      sections,
    })
    return {
      path: relativePath,
      previewToken: token,
      expiresAt: new Date(expiresAtMs).toISOString(),
      sections: sections.map(toPublicSection),
    }
  }

  async mutate(
    rawRootPath: string | null,
    owner: unknown,
    input: DesktopChangeMutationInput,
  ): Promise<DesktopChangeMutationResult> {
    const rootPath = requireWorkspaceRoot(rawRootPath)
    const snapshot = this.previews.get(input.previewToken)
    if (!snapshot || snapshot.owner !== owner || snapshot.rootPath !== rootPath) {
      throw new ChangeReviewError('PREVIEW_NOT_FOUND', 'change preview is not available')
    }
    if (snapshot.expiresAtMs <= this.now()) {
      this.previews.delete(input.previewToken)
      throw new ChangeReviewError('PREVIEW_EXPIRED', 'change preview has expired')
    }
    const hunkIds = validateHunkIds(input.hunkIds)
    const selected = selectMutationHunks(snapshot, input.action, hunkIds)
    const status = await this.requireReadyStatus(rootPath)
    const file = status.files.find((item) => item.path === snapshot.path)
    if (!file) throw new ChangeReviewError('PREVIEW_STALE', 'workspace changed after preview')
    const currentSections = await this.readDiffSections(rootPath, file)
    const currentSection = currentSections.find((section) => section.mode === selected.section.mode)
    if (!currentSection || currentSection.patchSha256 !== selected.section.patchSha256) {
      throw new ChangeReviewError('PREVIEW_STALE', 'workspace changed after preview')
    }
    if (snapshot.untracked && input.action === 'stage') {
      const allHunkIds = selected.section.internalHunks.map((hunk) => hunk.id)
      if (hunkIds.length !== allHunkIds.length || allHunkIds.some((id) => !hunkIds.includes(id))) {
        throw new ChangeReviewError(
          'UNTRACKED_PARTIAL_UNSUPPORTED',
          'untracked files must be staged as a complete file',
        )
      }
    }

    const operationId = randomUUID()
    const auditBase: Omit<ChangeReviewAuditRecord, 'phase'> = {
      operationId,
      action: input.action,
      path: snapshot.path,
      hunkIds,
      previewSha256: snapshot.previewSha256,
      auditContext: normalizeAuditContext(input.auditContext),
    }
    let requestedReceipt: ChangeReviewAuditReceipt
    try {
      requestedReceipt = await this.auditRecorder({ ...auditBase, phase: 'requested' })
      if (!requestedReceipt.accepted) throw new Error('audit request was not accepted')
    } catch {
      throw new ChangeReviewError('AUDIT_UNAVAILABLE', 'change mutation audit is unavailable')
    }

    const patch = buildSelectedPatch(selected.section, selected.hunks)
    let mutationApplied = false
    try {
      await this.applyMutation(rootPath, snapshot, input.action, patch)
      mutationApplied = true
    } catch (error) {
      await this.recordFailedAudit(auditBase, error)
      if (error instanceof ChangeReviewError) throw error
      throw new ChangeReviewError('GIT_MUTATION_FAILED', 'Git change mutation failed')
    }

    let completedReceipt: ChangeReviewAuditReceipt
    try {
      completedReceipt = await this.recordCompletedAudit(auditBase)
    } catch {
      if (mutationApplied) {
        try {
          await this.rollbackMutation(rootPath, snapshot, input.action, patch)
        } catch {
          throw new ChangeReviewError(
            'AUDIT_ROLLBACK_FAILED',
            'change audit failed and the Git rollback did not complete',
          )
        }
      }
      throw new ChangeReviewError(
        'AUDIT_COMPLETION_FAILED',
        'change audit failed; the Git mutation was rolled back',
      )
    } finally {
      this.previews.delete(input.previewToken)
    }

    return {
      action: input.action,
      path: snapshot.path,
      status: 'completed',
      updatedAt: new Date(this.now()).toISOString(),
      auditId: completedReceipt.auditId || requestedReceipt.auditId,
      eventId: completedReceipt.eventId,
    }
  }

  private async resolveRepository(rootPath: string): Promise<DesktopChangeReviewStatus> {
    const result = await this.gitRunner(
      rootPath,
      ['rev-parse', '--show-toplevel'],
      { allowedExitCodes: [0, 128] },
    )
    if (result.exitCode !== 0) {
      if (result.stderr.toLowerCase().includes('not a git repository')) {
        return emptyStatus('not-repository', rootPath)
      }
      throw new ChangeReviewError(
        'GIT_COMMAND_FAILED',
        sanitizeGitMessage(rootPath, result.stderr) || 'Git repository check failed',
      )
    }
    const reportedRoot = path.resolve(rootPath, result.stdout.trim())
    let repositoryRoot: string
    try {
      repositoryRoot = fs.realpathSync(reportedRoot)
    } catch {
      throw new ChangeReviewError('REPOSITORY_ROOT_INVALID', 'Git repository root is unavailable')
    }
    if (repositoryRoot !== rootPath) {
      throw new ChangeReviewError(
        'REPOSITORY_ROOT_OUTSIDE_WORKSPACE',
        'workspace root must be the Git repository root',
      )
    }
    return {
      ...emptyStatus('ready', rootPath),
      repositoryRoot,
    }
  }

  private async requireRepository(rootPath: string): Promise<string> {
    const repository = await this.resolveRepository(rootPath)
    if (repository.state !== 'ready' || !repository.repositoryRoot) {
      throw new ChangeReviewError('NOT_REPOSITORY', 'workspace root is not a Git repository')
    }
    return repository.repositoryRoot
  }

  private async requireReadyStatus(rootPath: string): Promise<DesktopChangeReviewStatus> {
    const status = await this.getStatus(rootPath)
    if (status.state !== 'ready') {
      throw new ChangeReviewError(status.errorCode || 'GIT_STATUS_UNAVAILABLE', status.message || 'Git status unavailable')
    }
    return status
  }

  private async readDiffSections(
    rootPath: string,
    file: DesktopChangeFile,
  ): Promise<InternalSection[]> {
    if (file.conflicted) return [conflictSection()]
    const sections: InternalSection[] = []
    if (file.staged) sections.push(await this.readDiffSection(rootPath, file, 'staged'))
    if (file.unstaged || file.untracked) {
      sections.push(await this.readDiffSection(rootPath, file, 'worktree'))
    }
    if (sections.length === 0) sections.push(emptySection('worktree'))
    return sections
  }

  private async readDiffSection(
    rootPath: string,
    file: DesktopChangeFile,
    mode: DesktopChangeDiffMode,
  ): Promise<InternalSection> {
    try {
      if (await this.isBinaryChange(rootPath, file, mode)) return binarySection(mode)
      const args = file.untracked && mode === 'worktree'
        ? [
            'diff', '--no-index', '--no-ext-diff', '--no-color', '--no-textconv',
            '--src-prefix=a/', '--dst-prefix=b/', '--', '/dev/null', file.path,
          ]
        : [
            'diff', ...(mode === 'staged' ? ['--cached'] : []), '--no-ext-diff', '--no-color',
            '--no-textconv', '--src-prefix=a/', '--dst-prefix=b/', '--', file.path,
          ]
      const result = await this.gitRunner(rootPath, args, {
        allowedExitCodes: file.untracked && mode === 'worktree' ? [0, 1] : [0],
      })
      return parseDiffSection(mode, normalizeUntrackedPatch(result.stdout, file.path))
    } catch (error) {
      if (error instanceof ChangeReviewError && error.code === 'GIT_OUTPUT_LIMIT') {
        return tooLargeSection(mode)
      }
      throw error
    }
  }

  private async isBinaryChange(
    rootPath: string,
    file: DesktopChangeFile,
    mode: DesktopChangeDiffMode,
  ): Promise<boolean> {
    if (file.untracked && mode === 'worktree') {
      const targetPath = validateWorkspacePath(rootPath, file.path)
      const descriptor = fs.openSync(path.join(rootPath, targetPath), 'r')
      try {
        const buffer = Buffer.alloc(BINARY_SNIFF_BYTES)
        const bytesRead = fs.readSync(descriptor, buffer, 0, buffer.byteLength, 0)
        return buffer.subarray(0, bytesRead).includes(0)
      } finally {
        fs.closeSync(descriptor)
      }
    }
    const result = await this.gitRunner(rootPath, [
      'diff',
      ...(mode === 'staged' ? ['--cached'] : []),
      '--numstat',
      '--no-ext-diff',
      '--no-textconv',
      '--',
      file.path,
    ])
    return result.stdout.split('\n').some((line) => line.startsWith('-\t-\t'))
  }

  private async applyMutation(
    rootPath: string,
    snapshot: PreviewSnapshot,
    action: DesktopChangeReviewAction,
    patch: string,
  ): Promise<void> {
    if (snapshot.untracked && action === 'stage') {
      await this.gitRunner(rootPath, ['add', '--', snapshot.path])
      return
    }
    await this.gitRunner(rootPath, gitApplyArgs(action), { input: patch })
    if (action === 'unstage') await this.removeEmptyIndexEntry(rootPath, snapshot.path)
  }

  private async rollbackMutation(
    rootPath: string,
    snapshot: PreviewSnapshot,
    action: DesktopChangeReviewAction,
    patch: string,
  ): Promise<void> {
    if (snapshot.untracked && action === 'stage') {
      await this.gitRunner(rootPath, ['rm', '--cached', '--quiet', '--ignore-unmatch', '--', snapshot.path])
      return
    }
    await this.gitRunner(rootPath, gitRollbackArgs(action), { input: patch })
  }

  private async removeEmptyIndexEntry(rootPath: string, relativePath: string): Promise<void> {
    const result = await this.gitRunner(
      rootPath,
      ['diff', '--cached', '--quiet', '--', relativePath],
      { allowedExitCodes: [0, 1] },
    )
    if (result.exitCode !== 0) return
    const status = await this.gitRunner(
      rootPath,
      ['status', '--porcelain=v1', '-z', '--untracked-files=all', '--', relativePath],
    )
    if (status.stdout.startsWith(' A ') || status.stdout.startsWith('A  ')) {
      await this.gitRunner(rootPath, ['rm', '--cached', '--quiet', '--ignore-unmatch', '--', relativePath])
    }
  }

  private async recordFailedAudit(
    auditBase: Omit<ChangeReviewAuditRecord, 'phase'>,
    error: unknown,
  ): Promise<void> {
    try {
      await this.auditRecorder({
        ...auditBase,
        phase: 'failed',
        errorCode: error instanceof ChangeReviewError ? error.code : 'GIT_MUTATION_FAILED',
      })
    } catch {
      // The requested audit record already proves intent; preserve the original Git failure.
    }
  }

  private async recordCompletedAudit(
    auditBase: Omit<ChangeReviewAuditRecord, 'phase'>,
  ): Promise<ChangeReviewAuditReceipt> {
    let lastError: unknown = new Error('audit completion was not accepted')
    for (let attempt = 0; attempt < COMPLETED_AUDIT_RECONCILIATION_ATTEMPTS; attempt += 1) {
      try {
        const receipt = await this.auditRecorder({ ...auditBase, phase: 'completed' })
        if (
          !receipt.accepted
          || receipt.operationId !== auditBase.operationId
          || receipt.phase !== 'completed'
        ) {
          throw new Error('audit completion was not accepted')
        }
        return receipt
      } catch (error) {
        lastError = error
        if (!isRetryableAuditReconciliationError(error)) break
      }
    }
    throw lastError
  }

  private prunePreviews(): void {
    const now = this.now()
    for (const [token, preview] of this.previews) {
      if (preview.expiresAtMs <= now) this.previews.delete(token)
    }
    while (this.previews.size >= MAX_PREVIEWS) {
      const oldest = this.previews.keys().next().value
      if (typeof oldest !== 'string') break
      this.previews.delete(oldest)
    }
  }
}

function isRetryableAuditReconciliationError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  const statusMatch = message.match(/API request failed:\s+(\d{3})\b/)
  if (!statusMatch) return true
  const status = Number(statusMatch[1])
  return status === 408 || status === 425 || status === 429 || status >= 500
}

export async function runGitCommand(
  rootPath: string,
  args: string[],
  options: GitCommandOptions = {},
): Promise<GitCommandResult> {
  const allowedExitCodes = options.allowedExitCodes ?? [0]
  const timeoutMs = options.timeoutMs ?? DEFAULT_GIT_TIMEOUT_MS
  const maxOutputBytes = options.maxOutputBytes ?? DEFAULT_GIT_OUTPUT_BYTES
  return await new Promise<GitCommandResult>((resolve, reject) => {
    const child = spawn('git', ['-C', rootPath, ...args], {
      cwd: rootPath,
      shell: false,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    const stdout: Buffer[] = []
    const stderr: Buffer[] = []
    let outputBytes = 0
    let settled = false
    let timedOut = false

    const settleReject = (error: Error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(error)
    }
    const onChunk = (bucket: Buffer[], chunk: Buffer) => {
      outputBytes += chunk.byteLength
      if (outputBytes > maxOutputBytes) {
        child.kill()
        settleReject(new ChangeReviewError('GIT_OUTPUT_LIMIT', 'Git output exceeded the safe limit'))
        return
      }
      bucket.push(chunk)
    }
    const timer = setTimeout(() => {
      timedOut = true
      child.kill()
      settleReject(new ChangeReviewError('GIT_TIMEOUT', 'Git command timed out'))
    }, timeoutMs)

    child.stdout.on('data', (chunk: Buffer) => onChunk(stdout, chunk))
    child.stderr.on('data', (chunk: Buffer) => onChunk(stderr, chunk))
    child.on('error', (error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') {
        settleReject(new ChangeReviewError('GIT_UNAVAILABLE', 'Git is not installed or unavailable'))
        return
      }
      settleReject(new ChangeReviewError('GIT_COMMAND_FAILED', 'Git command could not start'))
    })
    child.on('close', (exitCode) => {
      if (settled || timedOut) return
      settled = true
      clearTimeout(timer)
      const result = {
        stdout: Buffer.concat(stdout).toString('utf8'),
        stderr: Buffer.concat(stderr).toString('utf8'),
        exitCode: exitCode ?? -1,
      }
      if (!allowedExitCodes.includes(result.exitCode)) {
        reject(new ChangeReviewError(
          'GIT_COMMAND_FAILED',
          sanitizeGitMessage(rootPath, result.stderr) || 'Git command failed',
        ))
        return
      }
      resolve(result)
    })
    if (options.input !== undefined) child.stdin.end(options.input)
    else child.stdin.end()
  })
}

async function recordChangeReviewAudit(
  record: ChangeReviewAuditRecord,
): Promise<ChangeReviewAuditReceipt> {
  const response = await apiRequest<{
    accepted: boolean
    audit_id: string
    event_id: string | null
    operation_id: string
    phase: ChangeReviewAuditPhase
  }>('/api/desktop/change-review/audit', {
    method: 'POST',
    body: JSON.stringify({
      operation_id: record.operationId,
      phase: record.phase,
      action: record.action,
      path: record.path,
      hunk_ids: record.hunkIds,
      preview_sha256: record.previewSha256,
      task_id: record.auditContext?.taskId,
      run_id: record.auditContext?.runId,
      approval_id: record.auditContext?.approvalId,
      error_code: record.errorCode,
    }),
  })
  return {
    accepted: response.accepted,
    auditId: response.audit_id,
    eventId: response.event_id,
    operationId: response.operation_id,
    phase: response.phase,
  }
}

function validateWorkspaceRoot(rawRootPath: string): string {
  const resolved = path.resolve(rawRootPath)
  let realPath: string
  try {
    if (!fs.statSync(resolved).isDirectory()) throw new Error('not a directory')
    realPath = fs.realpathSync(resolved)
  } catch {
    throw new ChangeReviewError('WORKSPACE_ROOT_INVALID', 'workspace root is unavailable')
  }
  return realPath
}

function requireWorkspaceRoot(rawRootPath: string | null): string {
  if (!rawRootPath) throw new ChangeReviewError('WORKSPACE_NOT_CONFIGURED', 'workspace root is not configured')
  return validateWorkspaceRoot(rawRootPath)
}

function validateWorkspacePath(rootPath: string, rawPath: string): string {
  const normalizedInput = rawPath.trim()
  if (!normalizedInput || path.isAbsolute(normalizedInput)) throwPathNotAllowed(rawPath)
  const candidate = path.resolve(rootPath, normalizedInput)
  const relative = path.relative(rootPath, candidate)
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) throwPathNotAllowed(rawPath)
  let current = rootPath
  for (const segment of relative.split(path.sep).filter(Boolean)) {
    current = path.join(current, segment)
    if (!fs.existsSync(current)) break
    if (fs.lstatSync(current).isSymbolicLink()) throwPathNotAllowed(rawPath)
  }
  return relative.replaceAll(path.sep, '/')
}

function throwPathNotAllowed(rawPath: string): never {
  throw new ChangeReviewError('PATH_NOT_ALLOWED', `path is not allowed: ${sanitizePath(rawPath)}`)
}

function sanitizePath(rawPath: string): string {
  const trimmed = rawPath.trim() || '.'
  if (path.isAbsolute(trimmed)) return path.basename(trimmed) || '.'
  return path.normalize(trimmed).replaceAll(path.sep, '/')
}

function sanitizeGitMessage(rootPath: string, stderr: string): string {
  return stderr.replaceAll(rootPath, '<workspace>').trim().slice(0, 500)
}

function emptyStatus(
  state: DesktopChangeReviewState,
  rootPath: string | null,
): DesktopChangeReviewStatus {
  return {
    state,
    rootPath,
    repositoryRoot: state === 'ready' ? rootPath : null,
    branch: null,
    upstream: null,
    ahead: 0,
    behind: 0,
    files: [],
    errorCode: null,
    message: null,
  }
}

function degradedStatus(rawRootPath: string, error: unknown): DesktopChangeReviewStatus {
  const normalized = error instanceof ChangeReviewError
    ? error
    : new ChangeReviewError('GIT_STATUS_FAILED', 'Git status could not be read')
  const state: DesktopChangeReviewState = normalized.code === 'GIT_UNAVAILABLE'
    ? 'git-unavailable'
    : normalized.code === 'NOT_REPOSITORY'
      ? 'not-repository'
      : 'error'
  return {
    ...emptyStatus(state, path.resolve(rawRootPath)),
    errorCode: normalized.code,
    message: normalized.message,
  }
}

function parseStatusOutput(output: string): { branch: BranchStatus; files: DesktopChangeFile[] } {
  const records = output.split('\0')
  let branch: BranchStatus = { branch: null, upstream: null, ahead: 0, behind: 0 }
  const files: DesktopChangeFile[] = []
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index]
    if (!record) continue
    if (record.startsWith('## ')) {
      branch = parseBranchStatus(record.slice(3))
      continue
    }
    if (record.length < 3) continue
    const indexStatus = record[0] ?? ' '
    const worktreeStatus = record[1] ?? ' '
    const currentPath = normalizeGitPath(record.slice(3))
    const renamed = indexStatus === 'R' || indexStatus === 'C' || worktreeStatus === 'R' || worktreeStatus === 'C'
    const previousPath = renamed ? normalizeGitPath(records[index + 1] ?? '') : null
    if (renamed) index += 1
    const statusCode = `${indexStatus}${worktreeStatus}`
    files.push({
      path: currentPath,
      previousPath,
      indexStatus,
      worktreeStatus,
      staged: indexStatus !== ' ' && indexStatus !== '?',
      unstaged: worktreeStatus !== ' ',
      untracked: statusCode === '??',
      conflicted: CONFLICT_CODES.has(statusCode),
    })
  }
  files.sort((left, right) => left.path.localeCompare(right.path))
  return { branch, files }
}

function normalizeGitPath(rawPath: string): string {
  const normalized = rawPath.replaceAll('\\', '/')
  if (!normalized || normalized.startsWith('/') || normalized.split('/').includes('..')) {
    throw new ChangeReviewError('PATH_NOT_ALLOWED', `path is not allowed: ${sanitizePath(rawPath)}`)
  }
  return normalized
}

function parseBranchStatus(raw: string): BranchStatus {
  if (raw.startsWith('No commits yet on ')) {
    return { branch: raw.slice('No commits yet on '.length), upstream: null, ahead: 0, behind: 0 }
  }
  if (raw.startsWith('Initial commit on ')) {
    return { branch: raw.slice('Initial commit on '.length), upstream: null, ahead: 0, behind: 0 }
  }
  const trackingStart = raw.indexOf('...')
  const branch = raw.startsWith('HEAD ') ? null : (trackingStart >= 0 ? raw.slice(0, trackingStart) : raw.split(' ')[0] || null)
  const tracking = trackingStart >= 0 ? raw.slice(trackingStart + 3) : ''
  const upstream = tracking ? tracking.split(' ')[0] || null : null
  const ahead = Number(raw.match(/\bahead (\d+)/)?.[1] ?? 0)
  const behind = Number(raw.match(/\bbehind (\d+)/)?.[1] ?? 0)
  return { branch, upstream, ahead, behind }
}

function parseDiffSection(mode: DesktopChangeDiffMode, patch: string): InternalSection {
  if (!patch.trim()) return emptySection(mode)
  if (patch.includes('Binary files ') || patch.includes('GIT binary patch')) return binarySection(mode)
  const lines = patch.replaceAll('\r\n', '\n').split('\n')
  const firstHunk = lines.findIndex((line) => line.startsWith('@@ '))
  if (firstHunk < 0) return emptySection(mode)
  const headerLines = lines.slice(0, firstHunk)
  const internalHunks: InternalHunk[] = []
  let cursor = firstHunk
  while (cursor < lines.length) {
    if (!lines[cursor]?.startsWith('@@ ')) {
      cursor += 1
      continue
    }
    const start = cursor
    cursor += 1
    while (cursor < lines.length && !lines[cursor]?.startsWith('@@ ')) cursor += 1
    const rawLines = lines.slice(start, cursor)
    while (rawLines.at(-1) === '') rawLines.pop()
    const header = rawLines[0] ?? ''
    const parsed = parseHunkHeader(header)
    const id = `${mode}:${internalHunks.length}`
    internalHunks.push({
      id,
      header,
      ...parsed,
      lines: rawLines.slice(1),
      raw: `${rawLines.join('\n')}\n`,
    })
  }
  if (internalHunks.length === 0) return emptySection(mode)
  const headerText = `${headerLines.join('\n')}\n`
  const fullPatch = `${headerText}${internalHunks.map((hunk) => hunk.raw).join('')}`
  return {
    mode,
    kind: 'text',
    headerLines,
    hunks: internalHunks.map(toPublicHunk),
    canStage: mode === 'worktree',
    canUnstage: mode === 'staged',
    canRevert: mode === 'worktree',
    message: null,
    fullPatch,
    patchSha256: sha256(fullPatch),
    headerText,
    internalHunks,
  }
}

function parseHunkHeader(header: string): Omit<DesktopChangeDiffHunk, 'id' | 'header' | 'lines'> {
  const match = header.match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/)
  if (!match) throw new ChangeReviewError('DIFF_PARSE_FAILED', 'Git returned an invalid diff hunk')
  return {
    oldStart: Number(match[1]),
    oldLines: Number(match[2] ?? 1),
    newStart: Number(match[3]),
    newLines: Number(match[4] ?? 1),
  }
}

function normalizeUntrackedPatch(patch: string, relativePath: string): string {
  if (!patch) return patch
  const escaped = relativePath.replaceAll('\\', '/')
  return patch
    .replace(/^diff --git a\/dev\/null b\//m, 'diff --git a/')
    .replace(/^--- a\/dev\/null$/m, '--- /dev/null')
    .replace(/^\+\+\+ b\/\.\//m, '+++ b/')
    .replace(`diff --git a/${escaped} b/./${escaped}`, `diff --git a/${escaped} b/${escaped}`)
}

function emptySection(mode: DesktopChangeDiffMode): InternalSection {
  return specialSection(mode, 'empty', '没有可显示的文本差异')
}

function binarySection(mode: DesktopChangeDiffMode): InternalSection {
  return specialSection(mode, 'binary', '二进制文件不支持分块操作')
}

function conflictSection(): InternalSection {
  return specialSection('worktree', 'conflict', '冲突文件仅支持只读查看')
}

function tooLargeSection(mode: DesktopChangeDiffMode): InternalSection {
  return specialSection(mode, 'too-large', 'Diff 超过安全读取上限')
}

function specialSection(
  mode: DesktopChangeDiffMode,
  kind: DesktopChangeDiffKind,
  message: string,
): InternalSection {
  return {
    mode,
    kind,
    headerLines: [],
    hunks: [],
    canStage: false,
    canUnstage: false,
    canRevert: false,
    message,
    fullPatch: '',
    patchSha256: sha256(`${mode}:${kind}`),
    headerText: '',
    internalHunks: [],
  }
}

function toPublicHunk(hunk: InternalHunk): DesktopChangeDiffHunk {
  return {
    id: hunk.id,
    header: hunk.header,
    oldStart: hunk.oldStart,
    oldLines: hunk.oldLines,
    newStart: hunk.newStart,
    newLines: hunk.newLines,
    lines: [...hunk.lines],
  }
}

function toPublicSection(section: InternalSection): DesktopChangeDiffSection {
  return {
    mode: section.mode,
    kind: section.kind,
    headerLines: [...section.headerLines],
    hunks: section.internalHunks.map(toPublicHunk),
    canStage: section.canStage,
    canUnstage: section.canUnstage,
    canRevert: section.canRevert,
    message: section.message,
  }
}

function validateHunkIds(rawIds: string[]): string[] {
  if (!Array.isArray(rawIds) || rawIds.length === 0 || rawIds.length > MAX_HUNKS_PER_MUTATION) {
    throw new ChangeReviewError('HUNK_SELECTION_INVALID', 'select at least one valid diff hunk')
  }
  const unique = [...new Set(rawIds)]
  if (unique.length !== rawIds.length || unique.some((id) => !/^(staged|worktree):\d+$/.test(id))) {
    throw new ChangeReviewError('HUNK_SELECTION_INVALID', 'select at least one valid diff hunk')
  }
  return unique
}

function selectMutationHunks(
  snapshot: PreviewSnapshot,
  action: DesktopChangeReviewAction,
  hunkIds: string[],
): { section: InternalSection; hunks: InternalHunk[] } {
  if (!['stage', 'unstage', 'revert'].includes(action)) {
    throw new ChangeReviewError('ACTION_NOT_ALLOWED', 'change action is not allowed')
  }
  const expectedMode: DesktopChangeDiffMode = action === 'unstage' ? 'staged' : 'worktree'
  const section = snapshot.sections.find((item) => item.mode === expectedMode)
  if (!section || section.kind !== 'text') {
    throw new ChangeReviewError('ACTION_NOT_ALLOWED', 'selected change cannot be mutated')
  }
  const hunks = hunkIds.map((id) => section.internalHunks.find((hunk) => hunk.id === id))
  if (hunks.some((hunk) => !hunk)) {
    throw new ChangeReviewError('HUNK_SELECTION_INVALID', 'selected diff hunk is not part of this preview')
  }
  return { section, hunks: hunks as InternalHunk[] }
}

function buildSelectedPatch(section: InternalSection, hunks: InternalHunk[]): string {
  return `${section.headerText}${hunks.map((hunk) => hunk.raw).join('')}`
}

function gitApplyArgs(action: DesktopChangeReviewAction): string[] {
  return [
    'apply',
    ...(action === 'stage' || action === 'unstage' ? ['--cached'] : []),
    ...(action === 'unstage' || action === 'revert' ? ['--reverse'] : []),
    '--recount',
    '--whitespace=nowarn',
  ]
}

function gitRollbackArgs(action: DesktopChangeReviewAction): string[] {
  return [
    'apply',
    ...(action === 'stage' || action === 'unstage' ? ['--cached'] : []),
    ...(action === 'stage' ? ['--reverse'] : []),
    '--recount',
    '--whitespace=nowarn',
  ]
}

function normalizeAuditContext(
  context: DesktopChangeReviewAuditContext | undefined,
): DesktopChangeReviewAuditContext | undefined {
  if (!context) return undefined
  const normalized = {
    taskId: context.taskId?.trim() || undefined,
    runId: context.runId?.trim() || undefined,
    approvalId: context.approvalId?.trim() || undefined,
  }
  return normalized.taskId || normalized.runId || normalized.approvalId ? normalized : undefined
}

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex')
}
