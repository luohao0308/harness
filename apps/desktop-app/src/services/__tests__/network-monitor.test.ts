/**
 * NetworkMonitor tests - GREEN phase
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { BrowserNetworkMonitor } from '../browser-network-monitor'
import type { NetworkMonitor, NetworkStatus } from '../network-monitor'

describe('NetworkMonitor', () => {
  let monitor: NetworkMonitor

  beforeEach(() => {
    // Create a real instance
    monitor = new BrowserNetworkMonitor()
  })

  afterEach(() => {
    monitor.stop()
    vi.restoreAllMocks()
  })

  describe('getStatus', () => {
    it('should return current network status', () => {
      const status = monitor.getStatus()

      expect(status).toHaveProperty('online')
      expect(status).toHaveProperty('lastChangeTimestamp')
      expect(typeof status.online).toBe('boolean')
      expect(typeof status.lastChangeTimestamp).toBe('string')
    })

    it('should return online=true when connected', () => {
      // Mock online state
      Object.defineProperty(window.navigator, 'onLine', {
        writable: true,
        value: true,
      })

      const status = monitor.getStatus()

      expect(status.online).toBe(true)
    })

    it('should return online=false when disconnected', () => {
      // Mock offline state
      Object.defineProperty(window.navigator, 'onLine', {
        writable: true,
        value: false,
      })

      const status = monitor.getStatus()

      expect(status.online).toBe(false)
    })
  })

  describe('isOnline', () => {
    it('should return true when online', () => {
      Object.defineProperty(window.navigator, 'onLine', {
        writable: true,
        value: true,
      })

      expect(monitor.isOnline()).toBe(true)
    })

    it('should return false when offline', () => {
      Object.defineProperty(window.navigator, 'onLine', {
        writable: true,
        value: false,
      })

      expect(monitor.isOnline()).toBe(false)
    })
  })

  describe('start', () => {
    it('should start monitoring network status', () => {
      const onOnline = vi.fn()

      expect(() => monitor.start(onOnline)).not.toThrow()
    })

    it('should call onOnline callback when network reconnects', async () => {
      const onOnline = vi.fn()

      monitor.start(onOnline)

      // Simulate offline -> online transition
      Object.defineProperty(window.navigator, 'onLine', {
        writable: true,
        value: true,
      })

      const event = new Event('online')
      window.dispatchEvent(event)

      // Wait for event to be processed
      await new Promise(resolve => setTimeout(resolve, 100))

      expect(onOnline).toHaveBeenCalled()
    })

    it('should not call onOnline when going offline', async () => {
      const onOnline = vi.fn()

      monitor.start(onOnline)

      // Simulate online -> offline transition
      Object.defineProperty(window.navigator, 'onLine', {
        writable: true,
        value: false,
      })

      const event = new Event('offline')
      window.dispatchEvent(event)

      await new Promise(resolve => setTimeout(resolve, 100))

      expect(onOnline).not.toHaveBeenCalled()
    })

    it('should allow multiple start calls without error', () => {
      const onOnline = vi.fn()

      expect(() => {
        monitor.start(onOnline)
        monitor.start(onOnline)
      }).not.toThrow()
    })
  })

  describe('stop', () => {
    it('should stop monitoring network status', () => {
      const onOnline = vi.fn()

      monitor.start(onOnline)
      expect(() => monitor.stop()).not.toThrow()
    })

    it('should not call onOnline after stop', async () => {
      const onOnline = vi.fn()

      monitor.start(onOnline)
      monitor.stop()

      // Simulate network reconnection
      const event = new Event('online')
      window.dispatchEvent(event)

      await new Promise(resolve => setTimeout(resolve, 100))

      expect(onOnline).not.toHaveBeenCalled()
    })

    it('should handle stop without start', () => {
      expect(() => monitor.stop()).not.toThrow()
    })
  })

  describe('integration', () => {
    it('should track network status changes over time', async () => {
      const onOnline = vi.fn()

      monitor.start(onOnline)

      // Initial status
      const initialStatus = monitor.getStatus()
      const initialTimestamp = initialStatus.lastChangeTimestamp

      // Wait a bit
      await new Promise(resolve => setTimeout(resolve, 10))

      // Trigger offline
      Object.defineProperty(window.navigator, 'onLine', {
        writable: true,
        value: false,
      })
      window.dispatchEvent(new Event('offline'))
      await new Promise(resolve => setTimeout(resolve, 50))

      const offlineStatus = monitor.getStatus()
      expect(offlineStatus.online).toBe(false)
      expect(offlineStatus.lastChangeTimestamp).not.toBe(initialTimestamp)

      // Trigger online
      Object.defineProperty(window.navigator, 'onLine', {
        writable: true,
        value: true,
      })
      window.dispatchEvent(new Event('online'))
      await new Promise(resolve => setTimeout(resolve, 50))

      const onlineStatus = monitor.getStatus()
      expect(onlineStatus.online).toBe(true)
      expect(onlineStatus.lastChangeTimestamp).not.toBe(offlineStatus.lastChangeTimestamp)
      expect(onOnline).toHaveBeenCalledTimes(1)

      monitor.stop()
    })
  })
})
