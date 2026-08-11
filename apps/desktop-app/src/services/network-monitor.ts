/**
 * NetworkMonitor - Interface for monitoring network status and triggering auto-sync
 */

export interface NetworkStatus {
  online: boolean
  lastChangeTimestamp: string
}

export interface NetworkMonitor {
  /**
   * Get current network status
   */
  getStatus(): NetworkStatus

  /**
   * Start monitoring network status
   * Calls onOnline callback when network reconnects
   */
  start(onOnline: () => void): void

  /**
   * Stop monitoring network status
   */
  stop(): void

  /**
   * Check if currently online
   */
  isOnline(): boolean
}
