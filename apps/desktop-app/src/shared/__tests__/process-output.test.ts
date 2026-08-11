import { EventEmitter } from 'node:events'
import { describe, expect, test } from 'vitest'
import { installProcessOutputErrorGuards } from '../process-output'

class TestWriteStream extends EventEmitter {
  readonly write = () => true
}

describe('process output guards', () => {
  test.each(['EIO', 'EPIPE'])('absorbs %s from a detached terminal stream', (code) => {
    const stdout = new TestWriteStream()
    const stderr = new TestWriteStream()
    installProcessOutputErrorGuards(
      stdout as unknown as NodeJS.WriteStream,
      stderr as unknown as NodeJS.WriteStream,
    )

    expect(() => stderr.emit('error', Object.assign(new Error(code), { code }))).not.toThrow()
  })

  test('does not hide unrelated process output failures and installs once', () => {
    const stdout = new TestWriteStream()
    const stderr = new TestWriteStream()
    installProcessOutputErrorGuards(
      stdout as unknown as NodeJS.WriteStream,
      stderr as unknown as NodeJS.WriteStream,
    )
    installProcessOutputErrorGuards(
      stdout as unknown as NodeJS.WriteStream,
      stderr as unknown as NodeJS.WriteStream,
    )

    expect(stderr.listenerCount('error')).toBe(1)
    expect(() => stderr.emit('error', Object.assign(new Error('access denied'), { code: 'EACCES' })))
      .toThrow('access denied')
  })
})
