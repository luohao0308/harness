export type EnterpriseCoverageCommand = string;

export type LiveProviderCheck = {
  name: string;
  status: "passed" | "failed" | "pending" | "skipped";
  reason: string;
};

export type EnterpriseCoverageReportOptions = {
  generatedAt?: string;
  liveProviderChecks?: LiveProviderCheck[];
};

export const defaultEnterpriseCoverageCommands: readonly EnterpriseCoverageCommand[];

export function buildEnterpriseCoverageReport(options?: EnterpriseCoverageReportOptions): {
  schema_version: "enterprise_left_sidebar_functional_coverage.v1";
  generated_at: string;
  sidebar: {
    page_count: number;
    routes: string[];
    dynamic_route_count: number;
    dynamic_routes: string[];
    uncovered_routes: string[];
    evidence_files: string[];
  };
  cross_feature: {
    chain_count: number;
    chains: string[];
    failed_chain_details: Array<{ chain: string; reason: string }>;
    evidence_file: string;
  };
  model_pricing: {
    schema_version: string | null;
    source_count: number;
    source_status: Record<string, number>;
    blocking_sources: Array<{ model: string; status: string }>;
    evidence_file: string;
  };
  live_provider_checks: LiveProviderCheck[];
  commands: EnterpriseCoverageCommand[];
};
