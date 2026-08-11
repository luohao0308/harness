const OUTPUT_GUARD = Symbol.for('com.harness.desktop.process-output-guard')

type GuardedWriteStream = NodeJS.WriteStream & {
  [OUTPUT_GUARD]?: boolean
}

export function installProcessOutputErrorGuards(
  stdout: NodeJS.WriteStream = process.stdout,
  stderr: NodeJS.WriteStream = process.stderr,
): void {
  installOutputErrorGuard(stdout)
  installOutputErrorGuard(stderr)
}

function installOutputErrorGuard(stream: GuardedWriteStream): void {
  if (stream[OUTPUT_GUARD]) return
  stream[OUTPUT_GUARD] = true
  stream.on('error', (error: NodeJS.ErrnoException) => {
    if (error.code === 'EIO' || error.code === 'EPIPE') return
    throw error
  })
}
