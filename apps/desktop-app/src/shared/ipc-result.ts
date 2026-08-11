export type IpcErrorPayload = {
  name: string
  message: string
  code?: string
  status?: number
}

export type IpcResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: IpcErrorPayload }

export async function captureIpcResult<T>(operation: () => T | Promise<T>): Promise<IpcResult<T>> {
  try {
    return { ok: true, value: await operation() }
  } catch (error) {
    return { ok: false, error: serializeIpcError(error) }
  }
}

function serializeIpcError(error: unknown): IpcErrorPayload {
  if (!(error instanceof Error)) {
    return { name: 'Error', message: String(error) }
  }

  const extended = error as Error & { code?: unknown; status?: unknown }
  return {
    name: error.name || 'Error',
    message: error.message,
    ...(typeof extended.code === 'string' ? { code: extended.code } : {}),
    ...(typeof extended.status === 'number' ? { status: extended.status } : {}),
  }
}
