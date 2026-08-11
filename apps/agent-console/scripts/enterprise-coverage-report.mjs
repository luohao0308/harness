import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const evidenceFiles = {
  navigation: "src/app/consoleNav.ts",
  routes: "src/app/routes.tsx",
  chains: "e2e/enterprise-harness-chains.spec.ts",
  pricing: "public/model_pricing_sources.json",
};

const requiredChainTitles = [
  "models flow into workspace, model calls, cost rollup, and eval cost gate",
  "tools are linked through run evidence, registry, and audit",
  "knowledge source grounds workspace, run detail, and observability",
  "workspace and team-created subagents share durable evidence surfaces",
  "data export chain preserves audit evidence",
];

export const defaultEnterpriseCoverageCommands = Object.freeze([
  "npm test -- --run --pool forks --poolOptions.forks.singleFork",
  "npm run lint -- --pretty false",
  "npm run build",
  "npx playwright test --project=chromium e2e/sidebar-enterprise.smoke.spec.ts e2e/enterprise-harness-chains.spec.ts e2e/model-pricing.enterprise.spec.ts",
  "cd ../../services/api-server && .venv/bin/python -m pytest tests/test_enterprise_harness_chains.py tests/test_model_pricing_sources.py tests/test_team_subagent_enterprise_flow.py tests/test_workspace_subagent_enterprise_flow.py -q",
  "cd ../.. && python3 scripts/validate-docs.py",
  "cd ../.. && git diff --check",
]);

export function buildEnterpriseCoverageReport(options = {}) {
  const generatedAt = options.generatedAt ?? new Date().toISOString();
  const navigationSource = readEvidence(evidenceFiles.navigation);
  const routesSource = readEvidence(evidenceFiles.routes);
  const chainsSource = readEvidence(evidenceFiles.chains);
  const pricingDocument = JSON.parse(readEvidence(evidenceFiles.pricing));

  const sidebarRoutes = unique(matches(navigationSource, /\bto:\s*"([^"]+)"/g));
  const declaredRoutes = unique([
    "/",
    ...matches(routesSource, /\bpath:\s*"([^"]+)"/g).map(normalizeRoutePath),
  ]);
  const dynamicRoutes = declaredRoutes.filter((route) => route.includes(":"));
  const declaredRoutePatterns = new Set(declaredRoutes.map(toRoutePattern));
  const uncoveredRoutes = sidebarRoutes.filter(
    (route) => !declaredRoutePatterns.has(toRoutePattern(route)),
  );

  const chainTitles = matches(chainsSource, /\btest\(\s*"([^"]+)"/g);
  const missingChains = requiredChainTitles.filter((title) => !chainTitles.includes(title));
  const pricingRows = Array.isArray(pricingDocument.rows) ? pricingDocument.rows : [];
  const sourceStatus = countBy(pricingRows, (row) => row.verification_status ?? "unknown");
  const blockingSources = pricingRows
    .filter((row) => !isVerifiedPricingSource(row))
    .map((row) => ({
      model: `${row.mapped_provider ?? row.provider ?? "unknown"}/${row.mapped_model ?? row.model ?? "unknown"}`,
      status: row.verification_status ?? "invalid_source",
    }));

  return {
    schema_version: "enterprise_left_sidebar_functional_coverage.v1",
    generated_at: generatedAt,
    sidebar: {
      page_count: sidebarRoutes.length,
      routes: sidebarRoutes,
      dynamic_route_count: dynamicRoutes.length,
      dynamic_routes: dynamicRoutes,
      uncovered_routes: uncoveredRoutes,
      evidence_files: [evidenceFiles.navigation, evidenceFiles.routes],
    },
    cross_feature: {
      chain_count: chainTitles.length,
      chains: chainTitles,
      failed_chain_details: missingChains.map((title) => ({
        chain: title,
        reason: "Required chain is not defined in the enterprise Playwright suite.",
      })),
      evidence_file: evidenceFiles.chains,
    },
    model_pricing: {
      schema_version: pricingDocument.schema_version ?? null,
      source_count: pricingRows.length,
      source_status: sourceStatus,
      blocking_sources: blockingSources,
      evidence_file: evidenceFiles.pricing,
    },
    live_provider_checks:
      options.liveProviderChecks ?? defaultLiveProviderChecks(process.env),
    commands: [...defaultEnterpriseCoverageCommands],
  };
}

function readEvidence(relativePath) {
  return readFileSync(path.join(APP_ROOT, relativePath), "utf8");
}

function matches(source, pattern) {
  return [...source.matchAll(pattern)].map((match) => match[1]);
}

function unique(values) {
  return [...new Set(values)];
}

function normalizeRoutePath(routePath) {
  return routePath === "/" ? routePath : `/${routePath.replace(/^\/+/, "")}`;
}

function toRoutePattern(routePath) {
  return routePath.replace(/:[^/]+/g, ":param");
}

function countBy(values, keyForValue) {
  return values.reduce((counts, value) => {
    const key = keyForValue(value);
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

function isVerifiedPricingSource(row) {
  return (
    row.verification_status === "verified" &&
    row.currency === "USD" &&
    row.unit === "per_1m_tokens" &&
    typeof row.official_url === "string" &&
    row.official_url.startsWith("https://") &&
    typeof row.source_hash === "string" &&
    /^[0-9a-f]{64}$/.test(row.source_hash)
  );
}

function defaultLiveProviderChecks(environment) {
  if (environment.HARNESS_LIVE_PROVIDER_TESTS === "1") {
    return [
      {
        name: "provider-gated model pricing checks",
        status: "pending",
        reason: "HARNESS_LIVE_PROVIDER_TESTS=1; run the provider-gated verification commands before release.",
      },
    ];
  }
  return [
    {
      name: "provider-gated model pricing checks",
      status: "skipped",
      reason: "Set HARNESS_LIVE_PROVIDER_TESTS=1 with provider credentials to run live checks.",
    },
  ];
}

function isDirectExecution() {
  const entry = process.argv[1];
  return entry && path.resolve(entry) === fileURLToPath(import.meta.url);
}

if (isDirectExecution()) {
  process.stdout.write(`${JSON.stringify(buildEnterpriseCoverageReport(), null, 2)}\n`);
}
