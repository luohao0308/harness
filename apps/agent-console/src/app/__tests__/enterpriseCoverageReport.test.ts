import { describe, expect, it } from "vitest";

import {
  buildEnterpriseCoverageReport,
  defaultEnterpriseCoverageCommands,
} from "../../../scripts/enterprise-coverage-report.mjs";

describe("enterprise coverage report", () => {
  it("summarizes the sidebar, chain, pricing, and live-check release evidence", () => {
    const report = buildEnterpriseCoverageReport({
      generatedAt: "2026-07-06T00:00:00.000Z",
    });

    expect(report.schema_version).toBe("enterprise_left_sidebar_functional_coverage.v1");
    expect(report.generated_at).toBe("2026-07-06T00:00:00.000Z");
    expect(report.sidebar.page_count).toBeGreaterThanOrEqual(22);
    expect(report.sidebar.dynamic_route_count).toBeGreaterThanOrEqual(9);
    expect(report.sidebar.uncovered_routes).toEqual([]);
    expect(report.cross_feature.chain_count).toBeGreaterThanOrEqual(5);
    expect(report.cross_feature.failed_chain_details).toEqual([]);
    expect(report.model_pricing.source_status.verified).toBeGreaterThanOrEqual(5);
    expect(report.model_pricing.blocking_sources).toEqual([]);
    expect(report.live_provider_checks).toContainEqual(
      expect.objectContaining({
        status: "skipped",
        reason: expect.stringContaining("HARNESS_LIVE_PROVIDER_TESTS"),
      }),
    );
    expect(report.commands).toEqual(defaultEnterpriseCoverageCommands);
  });
});
