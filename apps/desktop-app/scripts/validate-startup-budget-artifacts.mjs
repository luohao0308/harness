import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

import { validateStartupEvidenceArtifacts } from './startup-evidence-lib.mjs'

const artifactsRoot = path.resolve(process.argv[2] || 'dist/desktop-evidence')
const outputPath = path.resolve(process.argv[3] || 'dist/desktop-startup-evidence.json')
const summary = await validateStartupEvidenceArtifacts(artifactsRoot, {
  releaseRef: process.env.GITHUB_REF_NAME || null,
})

await mkdir(path.dirname(outputPath), { recursive: true })
await writeFile(outputPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8')
process.stdout.write(
  `Desktop startup evidence passed for ${summary.reports.length} platforms at app version ${summary.app_version}.\n`,
)
process.stdout.write(`Desktop startup evidence summary: ${outputPath}\n`)
