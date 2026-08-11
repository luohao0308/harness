import { net, protocol } from 'electron'
import * as fs from 'node:fs'
import * as path from 'path'
import { pathToFileURL } from 'url'

export const RENDERER_SCHEME = 'harness-app'
export const RENDERER_HOST = 'renderer'
export const PACKAGED_RENDERER_URL = `${RENDERER_SCHEME}://${RENDERER_HOST}/index.html`
const RECOVERY_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Harness Desktop Recovery</title></head>
<body style="margin:0;font:14px system-ui;background:#f8fafc;color:#0f172a;display:grid;min-height:100vh;place-items:center">
<main style="max-width:440px;padding:24px"><h1 style="font-size:18px">Harness Desktop could not load</h1>
<p style="line-height:1.6;color:#475569">The packaged recovery files are unavailable. Restart Harness Desktop or reinstall the application.</p></main>
</body></html>`

export function registerRendererSchemePrivileges(): void {
  protocol?.registerSchemesAsPrivileged?.([
    {
      scheme: RENDERER_SCHEME,
      privileges: {
        standard: true,
        secure: true,
        supportFetchAPI: true,
        corsEnabled: true,
        stream: true,
      },
    },
  ])
}

export function registerRendererProtocol(): void {
  if (!protocol?.handle) return

  const rendererRoot = resolvePackagedRendererRoot()
  protocol.handle(RENDERER_SCHEME, (request) => {
    const url = new URL(request.url)
    if (url.hostname !== RENDERER_HOST) {
      return new Response('Not found', { status: 404 })
    }

    let relativePath: string
    try {
      relativePath = decodeURIComponent(url.pathname).replace(/^\/+/, '') || 'index.html'
    } catch {
      return new Response('Not found', { status: 404 })
    }
    if (!rendererRoot) {
      return relativePath === 'index.html' ? recoveryResponse() : new Response('Not found', { status: 404 })
    }
    const filePath = path.resolve(rendererRoot, relativePath)
    if (filePath !== rendererRoot && !filePath.startsWith(`${rendererRoot}${path.sep}`)) {
      return new Response('Not found', { status: 404 })
    }
    if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
      return relativePath === 'index.html' ? recoveryResponse() : new Response('Not found', { status: 404 })
    }
    return net.fetch(pathToFileURL(filePath).toString()).catch(() => {
      return relativePath === 'index.html' ? recoveryResponse() : new Response('Not found', { status: 404 })
    })
  })
}

export function resolvePackagedRendererRoot(
  resourcesPath = process.resourcesPath,
  bundledRoot = path.resolve(__dirname, '../renderer'),
): string | null {
  const candidates = [
    typeof resourcesPath === 'string' ? path.join(resourcesPath, 'renderer') : '',
    bundledRoot,
  ]
  return candidates.find((candidate) => candidate && fs.existsSync(path.join(candidate, 'index.html'))) || null
}

function recoveryResponse(): Response {
  return new Response(RECOVERY_HTML, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'",
    },
  })
}
