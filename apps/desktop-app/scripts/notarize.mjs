import { notarize } from '@electron/notarize'
import path from 'node:path'

function hasApiKeyCredentials(env) {
  return Boolean(env.APPLE_API_KEY && env.APPLE_API_KEY_ID && env.APPLE_API_ISSUER)
}

function hasAppleIdCredentials(env) {
  return Boolean(env.APPLE_ID && env.APPLE_APP_SPECIFIC_PASSWORD && env.APPLE_TEAM_ID)
}

export default async function notarizeMac(context) {
  const { electronPlatformName, appOutDir, packager } = context
  if (electronPlatformName !== 'darwin') return

  const appName = packager.appInfo.productFilename
  const appBundleId = packager.appInfo.appId
  const appPath = path.join(appOutDir, `${appName}.app`)

  if (hasApiKeyCredentials(process.env)) {
    await notarize({
      appBundleId,
      appPath,
      appleApiKey: process.env.APPLE_API_KEY,
      appleApiKeyId: process.env.APPLE_API_KEY_ID,
      appleApiIssuer: process.env.APPLE_API_ISSUER,
    })
    return
  }

  if (hasAppleIdCredentials(process.env)) {
    await notarize({
      appBundleId,
      appPath,
      appleId: process.env.APPLE_ID,
      appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
      teamId: process.env.APPLE_TEAM_ID,
    })
    return
  }

  console.log('Skipping macOS notarization: Apple notarization credentials are not configured.')
}
