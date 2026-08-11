import { app } from 'electron'

let ownsSingleInstance: boolean | null = null

export function ensureSingleInstanceLock(): boolean {
  if (ownsSingleInstance === null) {
    ownsSingleInstance = app.requestSingleInstanceLock()
  }
  return ownsSingleInstance
}
