import { describe, expect, it } from "vitest";

import { chartOptionFromArtifactData } from "../lib/chartArtifacts";

describe("chart artifact parsing", () => {
  it("converts Harness line chart data into an ECharts option", () => {
    const option = chartOptionFromArtifactData({
      chartType: "line",
      xAxis: ["Mon", "Tue"],
      series: [{ name: "Latency", data: [12, 18] }],
    });

    expect(option).toMatchObject({
      xAxis: { type: "category", data: ["Mon", "Tue"] },
      yAxis: { type: "value" },
      series: [{ name: "Latency", type: "line", data: [12, 18] }],
    });
  });

  it("accepts direct ECharts options", () => {
    const option = chartOptionFromArtifactData({
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: ["A"] },
      yAxis: { type: "value" },
      series: [{ type: "bar", data: [7] }],
    });

    expect(option).toMatchObject({
      xAxis: { type: "category", data: ["A"] },
      series: [{ type: "bar", data: [7] }],
    });
  });
});
