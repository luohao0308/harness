import type { EChartsOption, SeriesOption } from "echarts";

const CHART_TYPES = new Set(["line", "bar", "pie"]);

export function chartOptionFromArtifactData(data: unknown): EChartsOption | null {
  const value = parsePossibleJson(data);
  const root = asRecord(value);
  if (!root) return null;

  const chartData = asRecord(root.data) ?? root;
  const chartType = typeof chartData.chartType === "string" ? chartData.chartType : "";
  if (!CHART_TYPES.has(chartType)) {
    return directEChartsOption(chartData);
  }

  if (chartType === "pie") {
    return pieChartOption(chartData);
  }

  return cartesianChartOption(chartData, chartType as "line" | "bar");
}

function directEChartsOption(value: Record<string, unknown>): EChartsOption | null {
  if (!Array.isArray(value.series) && !asRecord(value.series)) return null;
  if (!asRecord(value.xAxis) && !Array.isArray(value.xAxis) && !asRecord(value.yAxis)) {
    return null;
  }
  if (Array.isArray(value.xAxis) && value.xAxis.some((item) => !asRecord(item))) {
    return null;
  }
  return value as EChartsOption;
}

function cartesianChartOption(
  value: Record<string, unknown>,
  chartType: "line" | "bar",
): EChartsOption | null {
  const labels = arrayFromUnknown(value.xAxis ?? value.labels ?? value.categories);
  const series = normalizeCartesianSeries(value.series, chartType);
  if (series.length === 0) return null;

  return {
    tooltip: { trigger: "axis" },
    grid: { left: 36, right: 16, top: 24, bottom: 32, containLabel: true },
    xAxis: { type: "category", data: labels.map((item) => String(item)) },
    yAxis: { type: "value" },
    series,
  };
}

function normalizeCartesianSeries(value: unknown, chartType: "line" | "bar"): SeriesOption[] {
  if (Array.isArray(value)) {
    const objectSeries = value
      .map((item, index) => {
        const record = asRecord(item);
        if (record && Array.isArray(record.data)) {
          return {
            ...record,
            type: record.type === "line" || record.type === "bar" ? record.type : chartType,
            name: typeof record.name === "string" ? record.name : `Series ${index + 1}`,
          } as SeriesOption;
        }
        if (typeof item === "number") {
          return null;
        }
        return null;
      })
      .filter(Boolean) as SeriesOption[];
    if (objectSeries.length > 0) return objectSeries;
    if (value.every((item) => typeof item === "number")) {
      return [{ type: chartType, data: value as number[], name: "Series 1" } as SeriesOption];
    }
  }

  const record = asRecord(value);
  if (record && Array.isArray(record.data)) {
    return [
      {
        ...record,
        type: record.type === "line" || record.type === "bar" ? record.type : chartType,
        name: typeof record.name === "string" ? record.name : "Series 1",
      } as SeriesOption,
    ];
  }
  return [];
}

function pieChartOption(value: Record<string, unknown>): EChartsOption | null {
  const data = normalizePieData(value.series ?? value.data);
  if (data.length === 0) return null;
  return {
    tooltip: { trigger: "item" },
    series: [
      {
        type: "pie",
        radius: ["35%", "70%"],
        center: ["50%", "52%"],
        data,
      },
    ],
  };
}

function normalizePieData(value: unknown): Array<{ name: string; value: number }> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item, index) => {
    const record = asRecord(item);
    if (record) {
      const numericValue = numberFromUnknown(record.value);
      if (numericValue === null) return [];
      return [
        {
          name: String(record.name ?? record.label ?? `Slice ${index + 1}`),
          value: numericValue,
        },
      ];
    }
    const numericValue = numberFromUnknown(item);
    return numericValue === null ? [] : [{ name: `Slice ${index + 1}`, value: numericValue }];
  });
}

function parsePossibleJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (!trimmed || !/^[\[{]/.test(trimmed)) return value;
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function arrayFromUnknown(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numberFromUnknown(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
