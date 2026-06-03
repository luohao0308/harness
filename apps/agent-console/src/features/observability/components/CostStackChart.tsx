import type { CostRollupSeriesPoint } from "../../tasks/api";

type Props = {
  points: CostRollupSeriesPoint[];
};

const COLORS = ["#0891b2", "#059669", "#d97706", "#dc2626", "#7c3aed", "#475569"];

export function CostStackChart({ points }: Props) {
  const buckets = Array.from(new Set(points.map((point) => point.bucket_start))).sort();
  const keys = Array.from(new Set(points.map((point) => point.key))).slice(0, COLORS.length);
  const maxBucketCost = Math.max(
    0,
    ...buckets.map((bucket) =>
      points
        .filter((point) => point.bucket_start === bucket && keys.includes(point.key))
        .reduce((sum, point) => sum + point.cost_usd, 0),
    ),
  );

  if (points.length === 0 || maxBucketCost <= 0) {
    return (
      <div className="flex h-56 items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50 text-xs text-slate-500">
        暂无成本时间序列
      </div>
    );
  }

  return (
    <div className="h-56 rounded-md border border-slate-100 bg-white p-3">
      <div className="flex h-44 items-end gap-1 overflow-hidden">
        {buckets.map((bucket) => {
          const bucketPoints = points.filter((point) => point.bucket_start === bucket);
          let stacked = 0;
          return (
            <div key={bucket} className="flex min-w-8 flex-1 flex-col justify-end gap-0.5">
              {keys.map((key, index) => {
                const value = bucketPoints.find((point) => point.key === key)?.cost_usd ?? 0;
                stacked += value;
                const height = Math.max(2, (value / maxBucketCost) * 168);
                return value > 0 ? (
                  <div
                    key={key}
                    title={`${key} $${value.toFixed(6)}`}
                    className="w-full rounded-sm"
                    style={{ height, backgroundColor: COLORS[index] }}
                  />
                ) : null;
              })}
              {stacked === 0 ? <div className="h-0.5 rounded-sm bg-slate-100" /> : null}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
        {keys.map((key, index) => (
          <span key={key} className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: COLORS[index] }} />
            {labelForKey(points, key)}
          </span>
        ))}
      </div>
    </div>
  );
}

function labelForKey(points: CostRollupSeriesPoint[], key: string) {
  return points.find((point) => point.key === key)?.label ?? key;
}
