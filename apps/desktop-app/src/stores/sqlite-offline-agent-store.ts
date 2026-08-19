import { randomUUID } from 'node:crypto'
import Database from 'better-sqlite3'
import type {
  DesktopOfflineAgentApproval,
  DesktopOfflineAgentEvent,
  DesktopOfflineAgentFileBaseline,
  DesktopOfflineAgentFileProposal,
  DesktopOfflineAgentModelCall,
  DesktopOfflineAgentRun,
  DesktopOfflineAgentRunInput,
  DesktopOfflineAgentSnapshot,
  DesktopOfflineAgentStatus,
  DesktopOfflineAgentToolCall,
  DesktopOfflineAgentToolName,
} from '../services/offline-agent-types'

export class SQLiteOfflineAgentStore {
  private db: Database.Database

  constructor(dbPath: string) {
    this.db = new Database(dbPath)
    this.db.pragma('journal_mode = WAL')
    this.db.pragma('foreign_keys = ON')
  }

  initialize(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS offline_agent_runs (
        id TEXT PRIMARY KEY,
        prompt TEXT NOT NULL,
        result TEXT,
        status TEXT NOT NULL CHECK(status IN (
          'PENDING', 'RUNNING', 'WAITING_APPROVAL', 'INTERRUPTED',
          'COMPLETED', 'FAILED', 'CANCELLED'
        )),
        model_source TEXT CHECK(model_source IN ('deterministic-local', 'local-model')),
        model_provider TEXT NOT NULL,
        model_name TEXT NOT NULL,
        model_requested INTEGER NOT NULL DEFAULT 0,
        fallback_reason TEXT,
        error_message TEXT,
        tool_request_json TEXT,
        pending_approval_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        sync_revision INTEGER NOT NULL DEFAULT 0
      );

      CREATE TABLE IF NOT EXISTS offline_agent_events (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES offline_agent_runs(id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        actor_type TEXT NOT NULL CHECK(actor_type IN ('system', 'user')),
        created_at TEXT NOT NULL,
        UNIQUE(run_id, sequence)
      );

      CREATE TABLE IF NOT EXISTS offline_agent_model_calls (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES offline_agent_runs(id) ON DELETE CASCADE,
        model_provider TEXT NOT NULL,
        model_name TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('SUCCESS', 'FAILED', 'CANCELLED')),
        duration_ms INTEGER NOT NULL DEFAULT 0,
        request_sha256 TEXT NOT NULL,
        response_text TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS offline_agent_tool_calls (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES offline_agent_runs(id) ON DELETE CASCADE,
        tool_name TEXT NOT NULL,
        risk_level TEXT NOT NULL CHECK(risk_level IN ('LOW', 'HIGH')),
        status TEXT NOT NULL CHECK(status IN (
          'PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'DENIED', 'CANCELLED'
        )),
        input_json TEXT NOT NULL,
        output_json TEXT NOT NULL,
        error_message TEXT,
        duration_ms INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS offline_agent_tool_approvals (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES offline_agent_runs(id) ON DELETE CASCADE,
        tool_call_id TEXT NOT NULL REFERENCES offline_agent_tool_calls(id) ON DELETE CASCADE,
        tool_name TEXT NOT NULL,
        risk_level TEXT NOT NULL CHECK(risk_level = 'HIGH'),
        status TEXT NOT NULL CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')),
        reason TEXT NOT NULL,
        request_json TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        decided_at TEXT
      );

      CREATE INDEX IF NOT EXISTS idx_offline_agent_runs_updated_at
        ON offline_agent_runs(updated_at DESC);
      CREATE INDEX IF NOT EXISTS idx_offline_agent_runs_status
        ON offline_agent_runs(status);
      CREATE INDEX IF NOT EXISTS idx_offline_agent_events_run_sequence
        ON offline_agent_events(run_id, sequence);
      CREATE INDEX IF NOT EXISTS idx_offline_agent_approvals_run_status
        ON offline_agent_tool_approvals(run_id, status);
    `)
  }

  createRun(input: DesktopOfflineAgentRunInput, modelProvider: string, modelName: string): DesktopOfflineAgentRun {
    const id = randomUUID()
    const now = new Date().toISOString()
    this.db.prepare(`
      INSERT INTO offline_agent_runs (
        id, prompt, result, status, model_source, model_provider, model_name,
        model_requested, fallback_reason, error_message, tool_request_json,
        pending_approval_id, created_at, updated_at, started_at, completed_at, sync_revision
      ) VALUES (?, ?, NULL, 'PENDING', NULL, ?, ?, ?, NULL, NULL, ?, NULL, ?, ?, NULL, NULL, 0)
    `).run(
      id,
      input.prompt,
      modelProvider,
      modelName,
      input.useLocalModel ? 1 : 0,
      input.toolRequest ? JSON.stringify(input.toolRequest) : null,
      now,
      now,
    )
    this.appendEvent(id, 'TASK_CREATED', { prompt: input.prompt, source: 'desktop-offline-agent' }, 'user')
    return this.requireRun(id)
  }

  getRun(id: string): DesktopOfflineAgentRun | null {
    const row = this.db.prepare('SELECT * FROM offline_agent_runs WHERE id = ?').get(id) as RunRow | undefined
    return row ? mapRun(row) : null
  }

  listRuns(limit = 50): DesktopOfflineAgentRun[] {
    const normalizedLimit = Math.max(1, Math.min(200, Math.floor(limit)))
    const rows = this.db.prepare(`
      SELECT * FROM offline_agent_runs ORDER BY datetime(updated_at) DESC, id DESC LIMIT ?
    `).all(normalizedLimit) as RunRow[]
    return rows.map(mapRun)
  }

  updateRun(
    id: string,
    updates: Partial<Pick<DesktopOfflineAgentRun,
      'status' | 'result' | 'modelSource' | 'fallbackReason' | 'errorMessage' |
      'pendingApprovalId' | 'startedAt' | 'completedAt'>>,
  ): DesktopOfflineAgentRun {
    this.requireRun(id)
    const fields: string[] = []
    const values: unknown[] = []
    const mappings: Array<[keyof typeof updates, string]> = [
      ['status', 'status'],
      ['result', 'result'],
      ['modelSource', 'model_source'],
      ['fallbackReason', 'fallback_reason'],
      ['errorMessage', 'error_message'],
      ['pendingApprovalId', 'pending_approval_id'],
      ['startedAt', 'started_at'],
      ['completedAt', 'completed_at'],
    ]
    for (const [key, column] of mappings) {
      if (updates[key] !== undefined) {
        fields.push(`${column} = ?`)
        values.push(updates[key])
      }
    }
    fields.push('updated_at = ?', 'sync_revision = sync_revision + 1')
    values.push(new Date().toISOString(), id)
    this.db.prepare(`UPDATE offline_agent_runs SET ${fields.join(', ')} WHERE id = ?`).run(...values)
    return this.requireRun(id)
  }

  appendEvent(
    runId: string,
    eventType: string,
    payload: Record<string, unknown>,
    actorType: 'system' | 'user' = 'system',
  ): DesktopOfflineAgentEvent {
    this.requireRun(runId)
    const sequenceRow = this.db.prepare(`
      SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
      FROM offline_agent_events WHERE run_id = ?
    `).get(runId) as { sequence: number }
    const event: DesktopOfflineAgentEvent = {
      id: randomUUID(),
      runId,
      sequence: sequenceRow.sequence,
      eventType,
      payload,
      actorType,
      createdAt: new Date().toISOString(),
    }
    this.db.prepare(`
      INSERT INTO offline_agent_events (
        id, run_id, sequence, event_type, payload_json, actor_type, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(event.id, event.runId, event.sequence, event.eventType, JSON.stringify(event.payload), event.actorType, event.createdAt)
    return event
  }

  listEvents(runId: string): DesktopOfflineAgentEvent[] {
    const rows = this.db.prepare(`
      SELECT * FROM offline_agent_events WHERE run_id = ? ORDER BY sequence ASC
    `).all(runId) as EventRow[]
    return rows.map(row => ({
      id: row.id,
      runId: row.run_id,
      sequence: row.sequence,
      eventType: row.event_type,
      payload: parseRecord(row.payload_json),
      actorType: row.actor_type as 'system' | 'user',
      createdAt: row.created_at,
    }))
  }

  addModelCall(input: Omit<DesktopOfflineAgentModelCall, 'id' | 'createdAt'>): DesktopOfflineAgentModelCall {
    const call: DesktopOfflineAgentModelCall = {
      ...input,
      id: randomUUID(),
      createdAt: new Date().toISOString(),
    }
    this.db.prepare(`
      INSERT INTO offline_agent_model_calls (
        id, run_id, model_provider, model_name, status, duration_ms,
        request_sha256, response_text, error_message, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      call.id, call.runId, call.modelProvider, call.modelName, call.status,
      call.durationMs, call.requestSha256, call.responseText, call.errorMessage, call.createdAt,
    )
    return call
  }

  listModelCalls(runId: string): DesktopOfflineAgentModelCall[] {
    const rows = this.db.prepare(`
      SELECT * FROM offline_agent_model_calls WHERE run_id = ? ORDER BY datetime(created_at), id
    `).all(runId) as ModelCallRow[]
    return rows.map(row => ({
      id: row.id,
      runId: row.run_id,
      modelProvider: row.model_provider,
      modelName: row.model_name,
      status: row.status as DesktopOfflineAgentModelCall['status'],
      durationMs: row.duration_ms,
      requestSha256: row.request_sha256,
      responseText: row.response_text,
      errorMessage: row.error_message,
      createdAt: row.created_at,
    }))
  }

  createToolCall(
    runId: string,
    toolName: DesktopOfflineAgentToolName,
    riskLevel: 'LOW' | 'HIGH',
    input: Record<string, unknown>,
  ): DesktopOfflineAgentToolCall {
    const now = new Date().toISOString()
    const call: DesktopOfflineAgentToolCall = {
      id: randomUUID(), runId, toolName, riskLevel, status: 'PENDING', input,
      output: {}, errorMessage: null, durationMs: 0, createdAt: now, updatedAt: now,
    }
    this.db.prepare(`
      INSERT INTO offline_agent_tool_calls (
        id, run_id, tool_name, risk_level, status, input_json, output_json,
        error_message, duration_ms, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?)
    `).run(call.id, runId, toolName, riskLevel, call.status, JSON.stringify(input), '{}', now, now)
    return call
  }

  updateToolCall(
    id: string,
    updates: Partial<Pick<DesktopOfflineAgentToolCall, 'status' | 'output' | 'errorMessage' | 'durationMs'>>,
  ): DesktopOfflineAgentToolCall {
    const fields: string[] = []
    const values: unknown[] = []
    if (updates.status !== undefined) { fields.push('status = ?'); values.push(updates.status) }
    if (updates.output !== undefined) { fields.push('output_json = ?'); values.push(JSON.stringify(updates.output)) }
    if (updates.errorMessage !== undefined) { fields.push('error_message = ?'); values.push(updates.errorMessage) }
    if (updates.durationMs !== undefined) { fields.push('duration_ms = ?'); values.push(updates.durationMs) }
    fields.push('updated_at = ?')
    values.push(new Date().toISOString(), id)
    this.db.prepare(`UPDATE offline_agent_tool_calls SET ${fields.join(', ')} WHERE id = ?`).run(...values)
    const row = this.db.prepare('SELECT * FROM offline_agent_tool_calls WHERE id = ?').get(id) as ToolCallRow | undefined
    if (!row) throw new Error('offline agent tool call not found')
    return mapToolCall(row)
  }

  listToolCalls(runId: string): DesktopOfflineAgentToolCall[] {
    return (this.db.prepare(`
      SELECT * FROM offline_agent_tool_calls WHERE run_id = ? ORDER BY datetime(created_at), id
    `).all(runId) as ToolCallRow[]).map(mapToolCall)
  }

  createApproval(toolCall: DesktopOfflineAgentToolCall, reason: string, target: DesktopOfflineAgentFileBaseline | null = null, proposal: DesktopOfflineAgentFileProposal | null = null): DesktopOfflineAgentApproval {
    const approval: DesktopOfflineAgentApproval = {
      id: randomUUID(),
      runId: toolCall.runId,
      toolCallId: toolCall.id,
      toolName: toolCall.toolName,
      riskLevel: 'HIGH',
      status: 'PENDING',
      reason,
      request: { toolName: toolCall.toolName, input: toolCall.input },
      target,
      proposal,
      decision: {},
      createdAt: new Date().toISOString(),
      decidedAt: null,
    }
    this.db.prepare(`
      INSERT INTO offline_agent_tool_approvals (
        id, run_id, tool_call_id, tool_name, risk_level, status, reason,
        request_json, decision_json, created_at, decided_at
      ) VALUES (?, ?, ?, ?, 'HIGH', 'PENDING', ?, ?, '{}', ?, NULL)
    `).run(
      approval.id, approval.runId, approval.toolCallId, approval.toolName,
      approval.reason, JSON.stringify({ ...approval.request, target, proposal }), approval.createdAt,
    )
    return approval
  }

  decideApproval(id: string, approved: boolean): DesktopOfflineAgentApproval {
    const decidedAt = new Date().toISOString()
    const status = approved ? 'APPROVED' : 'REJECTED'
    const result = this.db.prepare(`
      UPDATE offline_agent_tool_approvals
      SET status = ?, decision_json = ?, decided_at = ?
      WHERE id = ? AND status = 'PENDING'
    `).run(status, JSON.stringify({ approved }), decidedAt, id)
    if (result.changes !== 1) throw new Error('offline agent approval is not pending')
    return this.requireApproval(id)
  }

  markApprovalConflict(id: string, conflict: Record<string, unknown>): DesktopOfflineAgentApproval {
    const result = this.db.prepare(`UPDATE offline_agent_tool_approvals
      SET status = 'PENDING', decision_json = ?, decided_at = NULL
      WHERE id = ? AND status IN ('PENDING', 'APPROVED')`).run(JSON.stringify({ approved: false, conflict }), id)
    if (result.changes !== 1) throw new Error('offline agent approval is no longer available')
    return this.requireApproval(id)
  }

  getApproval(id: string): DesktopOfflineAgentApproval | null {
    const row = this.db.prepare('SELECT * FROM offline_agent_tool_approvals WHERE id = ?').get(id) as ApprovalRow | undefined
    return row ? mapApproval(row) : null
  }

  listApprovals(runId: string): DesktopOfflineAgentApproval[] {
    return (this.db.prepare(`
      SELECT * FROM offline_agent_tool_approvals WHERE run_id = ? ORDER BY datetime(created_at), id
    `).all(runId) as ApprovalRow[]).map(mapApproval)
  }

  recoverInterruptedRuns(): DesktopOfflineAgentRun[] {
    const recover = this.db.transaction(() => {
      const rows = this.db.prepare(`
        SELECT id FROM offline_agent_runs WHERE status IN ('PENDING', 'RUNNING')
      `).all() as Array<{ id: string }>
      for (const row of rows) {
        this.updateRun(row.id, { status: 'INTERRUPTED', errorMessage: 'desktop restarted during offline execution' })
        this.appendEvent(row.id, 'TASK_PAUSED', { reason: 'desktop_restart_recovery' })
      }
      return rows.map(row => this.requireRun(row.id))
    })
    return recover()
  }

  snapshot(runId: string): DesktopOfflineAgentSnapshot {
    return {
      schemaVersion: 1,
      run: this.requireRun(runId),
      events: this.listEvents(runId),
      modelCalls: this.listModelCalls(runId),
      toolCalls: this.listToolCalls(runId),
      approvals: this.listApprovals(runId),
    }
  }

  close(): void {
    this.db.close()
  }

  private requireRun(id: string): DesktopOfflineAgentRun {
    const run = this.getRun(id)
    if (!run) throw new Error('offline agent run not found')
    return run
  }

  private requireApproval(id: string): DesktopOfflineAgentApproval {
    const approval = this.getApproval(id)
    if (!approval) throw new Error('offline agent approval not found')
    return approval
  }
}

type RunRow = {
  id: string; prompt: string; result: string | null; status: DesktopOfflineAgentStatus
  model_source: 'deterministic-local' | 'local-model' | null; model_provider: string; model_name: string
  model_requested: number; fallback_reason: string | null; error_message: string | null
  tool_request_json: string | null; pending_approval_id: string | null; created_at: string; updated_at: string
  started_at: string | null; completed_at: string | null; sync_revision: number
}

type EventRow = {
  id: string; run_id: string; sequence: number; event_type: string; payload_json: string
  actor_type: string; created_at: string
}

type ModelCallRow = {
  id: string; run_id: string; model_provider: string; model_name: string; status: string
  duration_ms: number; request_sha256: string; response_text: string | null
  error_message: string | null; created_at: string
}

type ToolCallRow = {
  id: string; run_id: string; tool_name: string; risk_level: string; status: string
  input_json: string; output_json: string; error_message: string | null; duration_ms: number
  created_at: string; updated_at: string
}

type ApprovalRow = {
  id: string; run_id: string; tool_call_id: string; tool_name: string; risk_level: string
  status: string; reason: string; request_json: string; decision_json: string
  created_at: string; decided_at: string | null
}

function mapRun(row: RunRow): DesktopOfflineAgentRun {
  return {
    id: row.id,
    prompt: row.prompt,
    result: row.result,
    status: row.status,
    modelSource: row.model_source,
    modelProvider: row.model_provider,
    modelName: row.model_name,
    modelRequested: Boolean(row.model_requested),
    fallbackReason: row.fallback_reason,
    errorMessage: row.error_message,
    toolRequest: row.tool_request_json
      ? JSON.parse(row.tool_request_json) as DesktopOfflineAgentRun['toolRequest']
      : null,
    pendingApprovalId: row.pending_approval_id,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    startedAt: row.started_at,
    completedAt: row.completed_at,
    syncRevision: row.sync_revision,
  }
}

function mapToolCall(row: ToolCallRow): DesktopOfflineAgentToolCall {
  return {
    id: row.id,
    runId: row.run_id,
    toolName: row.tool_name as DesktopOfflineAgentToolName,
    riskLevel: row.risk_level as 'LOW' | 'HIGH',
    status: row.status as DesktopOfflineAgentToolCall['status'],
    input: parseRecord(row.input_json),
    output: parseRecord(row.output_json),
    errorMessage: row.error_message,
    durationMs: row.duration_ms,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}

function mapApproval(row: ApprovalRow): DesktopOfflineAgentApproval {
  const request = parseRecord(row.request_json)
  return {
    id: row.id,
    runId: row.run_id,
    toolCallId: row.tool_call_id,
    toolName: row.tool_name as DesktopOfflineAgentToolName,
    riskLevel: 'HIGH',
    status: row.status as DesktopOfflineAgentApproval['status'],
    reason: row.reason,
    request,
    target: request.target && typeof request.target === 'object'
      ? request.target as DesktopOfflineAgentApproval['target']
      : null,
    proposal: request.proposal && typeof request.proposal === 'object'
      ? request.proposal as DesktopOfflineAgentApproval['proposal']
      : null,
    decision: parseRecord(row.decision_json),
    createdAt: row.created_at,
    decidedAt: row.decided_at,
  }
}

function parseRecord(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
    ? parsed as Record<string, unknown>
    : {}
}
