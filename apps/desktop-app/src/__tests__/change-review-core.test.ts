import { execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { afterEach, describe, expect, test, vi } from 'vitest'

import {
  ChangeReviewError,
  ChangeReviewService,
  type ChangeReviewAuditRecord,
  type GitCommandRunner,
} from '../services/change-review-core'

const roots: string[] = []

function git(root: string, ...args: string[]): string {
  return execFileSync('git', ['-C', root, ...args], { encoding: 'utf8' })
}

function createRepository(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-change-review-'))
  roots.push(root)
  git(root, 'init', '-b', 'main')
  git(root, 'config', 'user.email', 'desktop@example.test')
  git(root, 'config', 'user.name', 'Desktop Test')
  fs.writeFileSync(
    path.join(root, 'tracked.txt'),
    Array.from({ length: 24 }, (_, index) => `line ${index + 1}`).join('\n') + '\n',
  )
  fs.writeFileSync(path.join(root, 'rename-old.txt'), 'rename me\n')
  fs.writeFileSync(path.join(root, 'delete-me.txt'), 'delete me\n')
  git(root, 'add', '.')
  git(root, 'commit', '-m', 'initial')
  return root
}

function writeTrackedChanges(root: string): void {
  const lines = fs.readFileSync(path.join(root, 'tracked.txt'), 'utf8').trimEnd().split('\n')
  lines[1] = 'line 2 changed'
  lines[20] = 'line 21 changed'
  fs.writeFileSync(path.join(root, 'tracked.txt'), `${lines.join('\n')}\n`)
}

function createAuditRecorder() {
  return vi.fn(async (record: ChangeReviewAuditRecord) => ({
    accepted: true,
    auditId: `audit-${record.phase}`,
    eventId: record.auditContext?.runId ? `event-${record.phase}` : null,
    operationId: record.operationId,
    phase: record.phase,
  }))
}

afterEach(() => {
  for (const root of roots.splice(0)) {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

describe('ChangeReviewService', () => {
  test('returns structured branch, staged, unstaged, untracked, deleted, and renamed status', async () => {
    const root = createRepository()
    writeTrackedChanges(root)
    fs.writeFileSync(path.join(root, 'staged.txt'), 'staged\n')
    fs.writeFileSync(path.join(root, 'untracked.txt'), 'untracked\n')
    fs.unlinkSync(path.join(root, 'delete-me.txt'))
    git(root, 'add', 'staged.txt')
    git(root, 'mv', 'rename-old.txt', 'rename-new.txt')

    const status = await new ChangeReviewService({ auditRecorder: createAuditRecorder() }).getStatus(root)

    expect(status).toMatchObject({
      state: 'ready',
      rootPath: fs.realpathSync(root),
      repositoryRoot: fs.realpathSync(root),
      branch: 'main',
    })
    expect(status.files).toEqual(expect.arrayContaining([
      expect.objectContaining({ path: 'tracked.txt', staged: false, unstaged: true }),
      expect.objectContaining({ path: 'staged.txt', staged: true, untracked: false }),
      expect.objectContaining({ path: 'untracked.txt', untracked: true, unstaged: true }),
      expect.objectContaining({ path: 'delete-me.txt', worktreeStatus: 'D' }),
      expect.objectContaining({ path: 'rename-new.txt', previousPath: 'rename-old.txt', staged: true }),
    ]))
    expect(status.files.map((file) => file.path)).toEqual(
      [...status.files.map((file) => file.path)].sort((left, right) => left.localeCompare(right)),
    )
  })

  test('returns text hunks and separate staged/worktree sections with opaque previews', async () => {
    const root = createRepository()
    writeTrackedChanges(root)
    const service = new ChangeReviewService({
      auditRecorder: createAuditRecorder(),
      tokenFactory: () => 'preview-token',
    })

    const diff = await service.getDiff(root, 'tracked.txt', 'window-1')

    expect(diff).toMatchObject({
      path: 'tracked.txt',
      previewToken: 'preview-token',
    })
    expect(diff.expiresAt).toMatch(/Z$/)
    expect(diff.sections).toHaveLength(1)
    expect(diff.sections[0]).toMatchObject({
      mode: 'worktree',
      kind: 'text',
      canStage: true,
      canUnstage: false,
      canRevert: true,
    })
    expect(diff.sections[0]?.hunks).toHaveLength(2)
    expect(diff.sections[0]?.hunks[0]).toMatchObject({
      id: 'worktree:0',
      oldStart: expect.any(Number),
      newStart: expect.any(Number),
      lines: expect.arrayContaining(['-line 2', '+line 2 changed']),
    })

    git(root, 'add', 'tracked.txt')
    const staged = await service.getDiff(root, 'tracked.txt', 'window-1')
    expect(staged.sections).toEqual([
      expect.objectContaining({
        mode: 'staged',
        kind: 'text',
        canStage: false,
        canUnstage: true,
        canRevert: false,
      }),
    ])
  })

  test('classifies binary and conflict changes without exposing mutable hunks', async () => {
    const root = createRepository()
    fs.writeFileSync(path.join(root, 'binary.bin'), Buffer.from([0, 1, 2, 3, 0, 4]))
    const service = new ChangeReviewService({ auditRecorder: createAuditRecorder() })

    const binary = await service.getDiff(root, 'binary.bin', 'window-1')
    expect(binary.sections).toEqual([
      expect.objectContaining({
        mode: 'worktree',
        kind: 'binary',
        hunks: [],
        canStage: false,
        canUnstage: false,
        canRevert: false,
      }),
    ])

    git(root, 'checkout', '-b', 'other')
    fs.writeFileSync(path.join(root, 'tracked.txt'), 'other branch\n')
    git(root, 'add', 'tracked.txt')
    git(root, 'commit', '-m', 'other change')
    git(root, 'checkout', 'main')
    fs.writeFileSync(path.join(root, 'tracked.txt'), 'main branch\n')
    git(root, 'add', 'tracked.txt')
    git(root, 'commit', '-m', 'main change')
    expect(() => git(root, 'merge', 'other')).toThrow()

    const status = await service.getStatus(root)
    expect(status.files).toEqual(expect.arrayContaining([
      expect.objectContaining({ path: 'tracked.txt', conflicted: true }),
    ]))
    const conflict = await service.getDiff(root, 'tracked.txt', 'window-1')
    expect(conflict.sections).toEqual([
      expect.objectContaining({ kind: 'conflict', hunks: [], canRevert: false }),
    ])
  })

  test('returns bounded degraded states for missing workspace, non-repository, unavailable Git, timeout, and output limit', async () => {
    const nonRepository = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-change-review-non-repo-'))
    roots.push(nonRepository)
    const service = new ChangeReviewService({ auditRecorder: createAuditRecorder() })

    await expect(service.getStatus(null)).resolves.toMatchObject({ state: 'no-workspace', files: [] })
    await expect(service.getStatus(nonRepository)).resolves.toMatchObject({
      state: 'not-repository',
      files: [],
    })

    for (const [code, state] of [
      ['GIT_UNAVAILABLE', 'git-unavailable'],
      ['GIT_TIMEOUT', 'error'],
      ['GIT_OUTPUT_LIMIT', 'error'],
    ] as const) {
      const runner: GitCommandRunner = vi.fn(async () => {
        throw new ChangeReviewError(code, 'bounded failure')
      })
      const degraded = await new ChangeReviewService({
        auditRecorder: createAuditRecorder(),
        gitRunner: runner,
      }).getStatus(nonRepository)
      expect(degraded).toMatchObject({ state, errorCode: code, message: 'bounded failure' })
    }
  })

  test('rejects lexical and symlink escapes with sanitized errors', async () => {
    const root = createRepository()
    const outside = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-change-review-outside-'))
    roots.push(outside)
    fs.writeFileSync(path.join(outside, 'secret.txt'), 'secret\n')
    fs.symlinkSync(path.join(outside, 'secret.txt'), path.join(root, 'secret-link.txt'))
    const service = new ChangeReviewService({ auditRecorder: createAuditRecorder() })

    await expect(service.getDiff(root, '../secret.txt', 'window-1')).rejects.toMatchObject({
      code: 'PATH_NOT_ALLOWED',
      message: 'path is not allowed: ../secret.txt',
    })
    await expect(service.getDiff(root, 'secret-link.txt', 'window-1')).rejects.toMatchObject({
      code: 'PATH_NOT_ALLOWED',
      message: 'path is not allowed: secret-link.txt',
    })

    try {
      await service.getDiff(root, 'secret-link.txt', 'window-1')
    } catch (error) {
      expect((error as Error).message).not.toContain(root)
      expect((error as Error).message).not.toContain(outside)
    }
  })

  test('stages, unstages, and reverts only selected current hunks with audit receipts', async () => {
    const root = createRepository()
    writeTrackedChanges(root)
    const auditRecorder = createAuditRecorder()
    const service = new ChangeReviewService({ auditRecorder })
    const context = { taskId: 'task-1', runId: 'task-1', approvalId: 'approval-1' }

    const initial = await service.getDiff(root, 'tracked.txt', 'window-1')
    const firstHunk = initial.sections[0]?.hunks[0]
    expect(firstHunk).toBeDefined()
    const staged = await service.mutate(root, 'window-1', {
      action: 'stage',
      previewToken: initial.previewToken,
      hunkIds: [firstHunk!.id],
      auditContext: context,
    })
    expect(staged).toMatchObject({ action: 'stage', path: 'tracked.txt', status: 'completed' })
    expect(git(root, 'diff', '--cached', '--', 'tracked.txt')).toContain('line 2 changed')
    expect(git(root, 'diff', '--cached', '--', 'tracked.txt')).not.toContain('line 21 changed')

    const stagedPreview = await service.getDiff(root, 'tracked.txt', 'window-1')
    const stagedHunk = stagedPreview.sections.find((section) => section.mode === 'staged')?.hunks[0]
    expect(stagedHunk).toBeDefined()
    await service.mutate(root, 'window-1', {
      action: 'unstage',
      previewToken: stagedPreview.previewToken,
      hunkIds: [stagedHunk!.id],
      auditContext: context,
    })
    expect(git(root, 'diff', '--cached', '--', 'tracked.txt')).toBe('')

    const revertPreview = await service.getDiff(root, 'tracked.txt', 'window-1')
    const revertHunk = revertPreview.sections
      .find((section) => section.mode === 'worktree')
      ?.hunks.find((hunk) => hunk.lines.includes('+line 2 changed'))
    expect(revertHunk).toBeDefined()
    await service.mutate(root, 'window-1', {
      action: 'revert',
      previewToken: revertPreview.previewToken,
      hunkIds: [revertHunk!.id],
      auditContext: context,
    })
    expect(fs.readFileSync(path.join(root, 'tracked.txt'), 'utf8')).toContain('line 2\n')
    expect(fs.readFileSync(path.join(root, 'tracked.txt'), 'utf8')).toContain('line 21 changed\n')
    expect(auditRecorder).toHaveBeenCalledWith(expect.objectContaining({ phase: 'requested' }))
    expect(auditRecorder).toHaveBeenCalledWith(expect.objectContaining({ phase: 'completed' }))
  })

  test('stages, unstages, and explicitly reverts an untracked file without implicit deletion', async () => {
    const root = createRepository()
    const target = path.join(root, 'untracked.txt')
    fs.writeFileSync(target, 'first\nsecond\n')
    const service = new ChangeReviewService({ auditRecorder: createAuditRecorder() })

    const untracked = await service.getDiff(root, 'untracked.txt', 'window-1')
    const untrackedHunks = untracked.sections[0]!.hunks.map((hunk) => hunk.id)
    await service.mutate(root, 'window-1', {
      action: 'stage',
      previewToken: untracked.previewToken,
      hunkIds: untrackedHunks,
    })
    expect(git(root, 'diff', '--cached', '--name-only')).toContain('untracked.txt')
    expect(fs.existsSync(target)).toBe(true)

    const staged = await service.getDiff(root, 'untracked.txt', 'window-1')
    const stagedHunks = staged.sections.find((section) => section.mode === 'staged')!.hunks.map((hunk) => hunk.id)
    await service.mutate(root, 'window-1', {
      action: 'unstage',
      previewToken: staged.previewToken,
      hunkIds: stagedHunks,
    })
    expect(git(root, 'diff', '--cached', '--name-only')).not.toContain('untracked.txt')
    expect(fs.existsSync(target)).toBe(true)

    const revert = await service.getDiff(root, 'untracked.txt', 'window-1')
    await service.mutate(root, 'window-1', {
      action: 'revert',
      previewToken: revert.previewToken,
      hunkIds: revert.sections[0]!.hunks.map((hunk) => hunk.id),
    })
    expect(fs.existsSync(target)).toBe(false)
  })

  test('rejects stale or cross-window previews before audit or mutation', async () => {
    const root = createRepository()
    writeTrackedChanges(root)
    const auditRecorder = createAuditRecorder()
    const service = new ChangeReviewService({ auditRecorder })
    const preview = await service.getDiff(root, 'tracked.txt', 'window-1')
    const hunkId = preview.sections[0]!.hunks[0]!.id

    await expect(service.mutate(root, 'window-2', {
      action: 'stage',
      previewToken: preview.previewToken,
      hunkIds: [hunkId],
    })).rejects.toMatchObject({ code: 'PREVIEW_NOT_FOUND' })

    fs.appendFileSync(path.join(root, 'tracked.txt'), 'late change\n')
    await expect(service.mutate(root, 'window-1', {
      action: 'stage',
      previewToken: preview.previewToken,
      hunkIds: [hunkId],
    })).rejects.toMatchObject({ code: 'PREVIEW_STALE' })
    expect(auditRecorder).not.toHaveBeenCalled()
    expect(git(root, 'diff', '--cached', '--', 'tracked.txt')).toBe('')
  })

  test('refuses mutation when audit preflight fails and rolls back when completion audit fails', async () => {
    const root = createRepository()
    writeTrackedChanges(root)
    const preflightFailure = vi.fn(async () => {
      throw new Error('audit offline')
    })
    const blocked = new ChangeReviewService({ auditRecorder: preflightFailure })
    const blockedPreview = await blocked.getDiff(root, 'tracked.txt', 'window-1')

    await expect(blocked.mutate(root, 'window-1', {
      action: 'stage',
      previewToken: blockedPreview.previewToken,
      hunkIds: [blockedPreview.sections[0]!.hunks[0]!.id],
    })).rejects.toMatchObject({ code: 'AUDIT_UNAVAILABLE' })
    expect(git(root, 'diff', '--cached', '--', 'tracked.txt')).toBe('')

    const completionFailure = vi.fn(async (record: ChangeReviewAuditRecord) => {
      if (record.phase === 'completed') throw new Error('completion audit offline')
      return {
        accepted: true,
        auditId: 'audit-requested',
        eventId: null,
        operationId: record.operationId,
        phase: record.phase,
      }
    })
    const rollback = new ChangeReviewService({ auditRecorder: completionFailure })
    const rollbackPreview = await rollback.getDiff(root, 'tracked.txt', 'window-1')
    await expect(rollback.mutate(root, 'window-1', {
      action: 'stage',
      previewToken: rollbackPreview.previewToken,
      hunkIds: [rollbackPreview.sections[0]!.hunks[0]!.id],
    })).rejects.toMatchObject({ code: 'AUDIT_COMPLETION_FAILED' })
    expect(git(root, 'diff', '--cached', '--', 'tracked.txt')).toBe('')
  })

  test('reconciles a lost completion response with the same operation before rollback', async () => {
    const root = createRepository()
    writeTrackedChanges(root)
    let completedAttempts = 0
    const operationIds: string[] = []
    const auditRecorder = vi.fn(async (record: ChangeReviewAuditRecord) => {
      operationIds.push(record.operationId)
      if (record.phase === 'completed') {
        completedAttempts += 1
        if (completedAttempts === 1) throw new Error('completion response was lost')
      }
      return {
        accepted: true,
        auditId: `audit-${record.phase}`,
        eventId: null,
        operationId: record.operationId,
        phase: record.phase,
      }
    })
    const service = new ChangeReviewService({ auditRecorder })
    const preview = await service.getDiff(root, 'tracked.txt', 'window-1')

    const result = await service.mutate(root, 'window-1', {
      action: 'stage',
      previewToken: preview.previewToken,
      hunkIds: [preview.sections[0]!.hunks[0]!.id],
    })

    expect(result.status).toBe('completed')
    expect(completedAttempts).toBe(2)
    expect(new Set(operationIds).size).toBe(1)
    expect(git(root, 'diff', '--cached', '--', 'tracked.txt')).not.toBe('')
  })
})
