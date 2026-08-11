import { ipcMain } from 'electron'
import type { Task, TaskStatus } from '../preload-api'
import { apiRequest, buildQueryString } from '../shared/api-client'

export function registerTaskHandlers(): void {
  ipcMain.handle('task:get', async (_event, taskId: string): Promise<Task> => {
    return apiRequest<Task>(`/api/tasks/${taskId}`)
  })

  ipcMain.handle('task:cancel', async (_event, taskId: string): Promise<void> => {
    await apiRequest(`/api/tasks/${taskId}/cancel`, {
      method: 'POST',
    })
  })

  ipcMain.handle(
    'task:list',
    async (
      _event,
      filters: { status?: TaskStatus } = {}
    ): Promise<{ items: Task[] }> => {
      const suffix = buildQueryString({
        status: filters.status,
      })

      return apiRequest<{ items: Task[] }>(`/api/tasks${suffix}`)
    }
  )
}
