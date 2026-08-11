import { describe, test, expect, vi, beforeEach } from 'vitest'
import { getApiBaseUrl, getAuthToken, apiRequest, buildQueryString } from '../api-client'

describe('api-client', () => {
  beforeEach(() => {
    vi.resetModules()
    delete process.env.API_BASE_URL
    delete process.env.AUTH_TOKEN
  })

  describe('getApiBaseUrl', () => {
    test('should return default URL when env var not set', () => {
      expect(getApiBaseUrl()).toBe('http://localhost:8000')
    })

    test('should return env var when set', () => {
      process.env.API_BASE_URL = 'https://api.example.com'
      expect(getApiBaseUrl()).toBe('https://api.example.com')
    })
  })

  describe('getAuthToken', () => {
    test('should return empty string when env var not set', () => {
      expect(getAuthToken()).toBe('')
    })

    test('should return env var when set', () => {
      process.env.AUTH_TOKEN = 'test-token-123'
      expect(getAuthToken()).toBe('test-token-123')
    })
  })

  describe('buildQueryString', () => {
    test('should return empty string for empty params', () => {
      expect(buildQueryString({})).toBe('')
    })

    test('should build query string from params', () => {
      const result = buildQueryString({ status: 'active', page: '1' })
      expect(result).toBe('?status=active&page=1')
    })

    test('should skip undefined values', () => {
      const result = buildQueryString({ status: 'active', page: undefined })
      expect(result).toBe('?status=active')
    })

    test('should return empty string when all values undefined', () => {
      const result = buildQueryString({ status: undefined, page: undefined })
      expect(result).toBe('')
    })
  })

  describe('apiRequest', () => {
    const mockFetch = vi.fn()

    beforeEach(() => {
      global.fetch = mockFetch
      mockFetch.mockReset()
    })

    test('should make successful GET request', async () => {
      const mockData = { id: '123', name: 'test' }
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockData,
      })

      const result = await apiRequest('/api/test')

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/test',
        expect.objectContaining({
          headers: {
            'Content-Type': 'application/json',
          },
        })
      )
      expect(result).toEqual(mockData)
    })

    test('should include auth token when set', async () => {
      process.env.AUTH_TOKEN = 'bearer-token-xyz'
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({}),
      })

      await apiRequest('/api/test')

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/test',
        expect.objectContaining({
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer bearer-token-xyz',
          },
        })
      )
    })

    test('should make POST request with body', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({}),
      })

      await apiRequest('/api/test', {
        method: 'POST',
        body: JSON.stringify({ data: 'test' }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/test',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ data: 'test' }),
        })
      )
    })

    test('should throw error on failed request', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      })

      await expect(apiRequest('/api/test')).rejects.toThrow(
        'API request failed: 404 Not Found'
      )
    })

    test('should use custom API_BASE_URL', async () => {
      process.env.API_BASE_URL = 'https://custom.api.com'
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({}),
      })

      await apiRequest('/api/test')

      expect(mockFetch).toHaveBeenCalledWith(
        'https://custom.api.com/api/test',
        expect.any(Object)
      )
    })
  })
})
