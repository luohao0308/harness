/**
 * BrowserNetworkMonitor - Browser-based implementation of NetworkMonitor
 */

import type { NetworkMonitor, NetworkStatus } from './network-monitor'

export class BrowserNetworkMonitor implements NetworkMonitor {
  private isMonitoring = false
  private lastChangeTimestamp: string = new Date().toISOString()
  private onOnlineCallback?: () => void

  getStatus(): NetworkStatus {
    return {
      online: this.isOnline(),
      lastChangeTimestamp: this.lastChangeTimestamp,
    }
  }

  isOnline(): boolean {
    return navigator.onLine
  }

  start(onOnline: () => void): void {
    // Prevent duplicate listeners
    if (this.isMonitoring) {
      return
    }

    this.isMonitoring = true
    this.onOnlineCallback = onOnline

    window.addEventListener('online', this.handleOnline)
    window.addEventListener('offline', this.handleOffline)
  }

  stop(): void {
    if (!this.isMonitoring) {
      return
    }

    this.isMonitoring = false
    this.onOnlineCallback = undefined

    window.removeEventListener('online', this.handleOnline)
    window.removeEventListener('offline', this.handleOffline)
  }

  private handleOnline = (): void => {
    this.lastChangeTimestamp = new Date().toISOString()

    if (this.onOnlineCallback) {
      this.onOnlineCallback()
    }
  }

  private handleOffline = (): void => {
    this.lastChangeTimestamp = new Date().toISOString()
  }
}
