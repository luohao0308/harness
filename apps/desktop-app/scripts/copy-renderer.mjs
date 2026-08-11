import { execFile } from 'node:child_process'
import { cp, mkdir, rm, stat } from 'node:fs/promises'
import path from 'node:path'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const appRoot = path.resolve(__dirname, '..')
const defaultSource = path.resolve(appRoot, '..', 'agent-console', 'dist')
const source = path.resolve(process.env.HARNESS_AGENT_CONSOLE_DIST || defaultSource)
const destination = path.resolve(appRoot, 'dist', 'renderer')
const execFileAsync = promisify(execFile)

async function buildDefaultRenderer() {
  if (process.env.HARNESS_AGENT_CONSOLE_DIST) return

  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
  const apiBaseUrl = process.env.VITE_API_BASE_URL || '/'
  const terminalWsUrl = process.env.VITE_TERMINAL_WS_URL || '/ws/terminal'
  const { stdout, stderr } = await execFileAsync(npmCommand, ['run', 'build'], {
    cwd: path.dirname(defaultSource),
    env: {
      ...process.env,
      HARNESS_DESKTOP_BUILD: '1',
      VITE_RUNTIME_PROFILE: 'local',
      VITE_API_BASE_URL: apiBaseUrl,
      VITE_DESKTOP_ROUTER: 'hash',
      VITE_TERMINAL_WS_URL: terminalWsUrl,
    },
    maxBuffer: 16 * 1024 * 1024,
  })
  if (stdout) process.stdout.write(stdout)
  if (stderr) process.stderr.write(stderr)
}

async function assertBuiltRenderer() {
  const indexPath = path.join(source, 'index.html')
  try {
    const info = await stat(indexPath)
    if (!info.isFile()) throw new Error('index.html is not a file')
  } catch (error) {
    throw new Error(
      `Agent Console renderer build is missing at ${source}. Run "cd ../agent-console && npm run build" first.`
    )
  }
}

await buildDefaultRenderer()
await assertBuiltRenderer()
await rm(destination, { recursive: true, force: true })
await mkdir(path.dirname(destination), { recursive: true })
await cp(source, destination, { recursive: true, force: true })
console.log(`Copied Agent Console renderer from ${source} to ${destination}`)
