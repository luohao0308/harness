import { execFile } from 'node:child_process'
import { access } from 'node:fs/promises'
import path from 'node:path'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'

const execFileAsync = promisify(execFile)
const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const desktopRoot = path.resolve(scriptDir, '..')
const serviceRoot = path.resolve(desktopRoot, '..', '..', 'services', 'api-server')
const venvPython = process.platform === 'win32'
  ? path.join(serviceRoot, '.venv', 'Scripts', 'python.exe')
  : path.join(serviceRoot, '.venv', 'bin', 'python')

let python = process.env.HARNESS_RUNTIME_PYTHON || venvPython
try {
  await access(python)
} catch {
  python = process.platform === 'win32' ? 'python.exe' : 'python3'
}

const { stdout, stderr } = await execFileAsync(
  python,
  [
    path.join(serviceRoot, 'scripts', 'build-harnessd.py'),
    '--dist-dir', path.join(desktopRoot, 'resources'),
  ],
  {
    cwd: serviceRoot,
    env: { ...process.env },
    maxBuffer: 32 * 1024 * 1024,
  },
)
if (stdout) process.stdout.write(stdout)
if (stderr) process.stderr.write(stderr)
