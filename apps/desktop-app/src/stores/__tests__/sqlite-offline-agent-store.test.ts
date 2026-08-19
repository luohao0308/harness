import { afterEach, beforeEach, describe, expect, test } from 'vitest'
import { SQLiteOfflineAgentStore } from '../sqlite-offline-agent-store'

describe('SQLiteOfflineAgentStore', () => {
  let store: SQLiteOfflineAgentStore

  beforeEach(() => {
    store = new SQLiteOfflineAgentStore(':memory:')
    store.initialize()
  })

  afterEach(() => store.close())

  test('persists a complete run evidence snapshot', () => {
    const run = store.createRun({
      prompt: 'Summarize the release evidence',
      useLocalModel: true,
      toolRequest: { name: 'workspace.read_text', input: { path: 'README.md' } },
    }, 'ollama', 'llama3.1')
    store.updateRun(run.id, { status: 'RUNNING', startedAt: '2026-08-19T00:00:00.000Z' })
    store.appendEvent(run.id, 'TASK_STARTED', { offline: true })
    const toolCall = store.createToolCall(run.id, 'workspace.write_text', 'HIGH', {
      path: 'report.txt', content: 'ready',
    })
    const approval = store.createApproval(toolCall, 'Writing workspace files requires approval')
    store.decideApproval(approval.id, true)
    store.updateToolCall(toolCall.id, { status: 'SUCCESS', output: { path: 'report.txt' }, durationMs: 2 })
    store.addModelCall({
      runId: run.id,
      modelProvider: 'ollama',
      modelName: 'llama3.1',
      status: 'SUCCESS',
      durationMs: 10,
      requestSha256: 'a'.repeat(64),
      responseText: 'done',
      errorMessage: null,
    })
    store.updateRun(run.id, {
      status: 'COMPLETED', result: 'done', modelSource: 'local-model',
      completedAt: '2026-08-19T00:00:01.000Z',
    })

    const snapshot = store.snapshot(run.id)
    expect(snapshot.run).toMatchObject({ status: 'COMPLETED', result: 'done', syncRevision: 2 })
    expect(snapshot.events.map(event => event.eventType)).toEqual(['TASK_CREATED', 'TASK_STARTED'])
    expect(snapshot.modelCalls).toHaveLength(1)
    expect(snapshot.toolCalls[0]).toMatchObject({ status: 'SUCCESS', toolName: 'workspace.write_text' })
    expect(snapshot.approvals[0]).toMatchObject({ status: 'APPROVED' })
  })

  test('marks unfinished runs interrupted while preserving pending approvals', () => {
    const running = store.createRun({ prompt: 'running' }, 'desktop', 'deterministic')
    store.updateRun(running.id, { status: 'RUNNING' })
    const waiting = store.createRun({ prompt: 'waiting' }, 'desktop', 'deterministic')
    store.updateRun(waiting.id, { status: 'WAITING_APPROVAL' })

    const recovered = store.recoverInterruptedRuns()

    expect(recovered.map(run => run.id)).toEqual([running.id])
    expect(store.getRun(running.id)).toMatchObject({
      status: 'INTERRUPTED', errorMessage: 'desktop restarted during offline execution',
    })
    expect(store.listEvents(running.id).at(-1)).toMatchObject({ eventType: 'TASK_PAUSED' })
    expect(store.getRun(waiting.id)?.status).toBe('WAITING_APPROVAL')
  })
})
