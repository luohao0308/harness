export const siteLinks = {
  console: process.env.NEXT_PUBLIC_CONSOLE_BASE_URL ?? "http://127.0.0.1:5173",
  api: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000",
  openapiJson: "/openapi.json",
  openapiYaml: "/openapi.yaml",
  usageFlow:
    "https://github.com/luohao0308/harness/blob/develop/docs/design/website-usage-flow.md",
  deployment:
    "https://github.com/luohao0308/harness/blob/develop/docs/project-memory/runbooks/deployment.md",
  localDevelopment:
    "https://github.com/luohao0308/harness/blob/develop/docs/project-memory/runbooks/local-development.md",
  troubleshooting:
    "https://github.com/luohao0308/harness/blob/develop/docs/project-memory/runbooks/troubleshooting.md",
};

export function consolePath(path: string) {
  return `${siteLinks.console}${path}`;
}
