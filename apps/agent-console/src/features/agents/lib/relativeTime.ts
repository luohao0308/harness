/**
 * Relative time formatter for message bubbles (Req 11.1 / 11.2 / 11.4).
 *
 * Implements {@link formatRelativeTime} and {@link formatLocalIso}:
 *   - `formatRelativeTime` prefers the browser's `Intl.RelativeTimeFormat`
 *     with `numeric: "auto"`; falls back to manual zh-CN / en bucket strings
 *     when the API is unavailable or throws.
 *   - Both functions are TOTAL: any input (including `NaN`, `Infinity`,
 *     negative numbers) is accepted without throwing.
 *
 * Design reference: design.md §New lib modules → `relativeTime.ts`.
 */

export type RelativeTimeLocale = "zh-CN" | "en";

type RelativeBucketUnit = "minute" | "hour" | "day" | "week" | "month" | "year";

const MINUTE_MS = 60 * 1000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;
const WEEK_MS = 7 * DAY_MS;
const MONTH_MS = 30 * DAY_MS;
const YEAR_MS = 365 * DAY_MS;

type RelativeBucket = {
  unit: RelativeBucketUnit;
  value: number;
};

function pickBucket(absMs: number): RelativeBucket | null {
  if (absMs < MINUTE_MS) return null;
  if (absMs < HOUR_MS) return { unit: "minute", value: Math.floor(absMs / MINUTE_MS) };
  if (absMs < DAY_MS) return { unit: "hour", value: Math.floor(absMs / HOUR_MS) };
  if (absMs < WEEK_MS) return { unit: "day", value: Math.floor(absMs / DAY_MS) };
  if (absMs < MONTH_MS) return { unit: "week", value: Math.floor(absMs / WEEK_MS) };
  if (absMs < YEAR_MS) return { unit: "month", value: Math.floor(absMs / MONTH_MS) };
  return { unit: "year", value: Math.floor(absMs / YEAR_MS) };
}

function justNow(locale: RelativeTimeLocale): string {
  return locale === "zh-CN" ? "刚刚" : "just now";
}

function zhUnitLabel(unit: RelativeBucketUnit): string {
  switch (unit) {
    case "minute":
      return "分钟";
    case "hour":
      return "小时";
    case "day":
      return "天";
    case "week":
      return "周";
    case "month":
      return "个月";
    case "year":
      return "年";
  }
}

function enUnitLabel(unit: RelativeBucketUnit, value: number): string {
  const plural = value === 1 ? "" : "s";
  switch (unit) {
    case "minute":
      return `min${plural}`;
    case "hour":
      return `hour${plural}`;
    case "day":
      return `day${plural}`;
    case "week":
      return `week${plural}`;
    case "month":
      return `month${plural}`;
    case "year":
      return `year${plural}`;
  }
}

function formatManualFallback(
  bucket: RelativeBucket,
  isPast: boolean,
  locale: RelativeTimeLocale,
): string {
  if (locale === "zh-CN") {
    const label = zhUnitLabel(bucket.unit);
    return isPast ? `${bucket.value} ${label}前` : `${bucket.value} ${label}后`;
  }
  const label = enUnitLabel(bucket.unit, bucket.value);
  return isPast ? `${bucket.value} ${label} ago` : `in ${bucket.value} ${label}`;
}

function tryFormatIntl(
  signedValue: number,
  unit: RelativeBucketUnit,
  locale: RelativeTimeLocale,
): string | null {
  const rtfCtor =
    typeof Intl !== "undefined" ? Intl.RelativeTimeFormat : undefined;
  if (typeof rtfCtor !== "function") return null;
  try {
    const rtf = new rtfCtor(locale === "zh-CN" ? "zh-CN" : "en", {
      numeric: "auto",
    });
    return rtf.format(signedValue, unit);
  } catch {
    return null;
  }
}

/**
 * Format the delta `targetMs - nowMs` as a localized relative-time string.
 *
 * TOTAL behaviour:
 *   - Non-finite inputs (`NaN`, `Infinity`, `-Infinity`) produce `""`.
 *   - `|diff| < 60s` produces `"刚刚"` / `"just now"`.
 *   - Past (`diff < 0`) produces `"N unit ago"` / `"N 单位前"`.
 *   - Future (`diff > 0`) produces `"in N unit"` / `"N 单位后"`.
 */
export function formatRelativeTime(
  targetMs: number,
  nowMs: number,
  locale: RelativeTimeLocale,
): string {
  if (!Number.isFinite(targetMs) || !Number.isFinite(nowMs)) return "";

  const diff = targetMs - nowMs;
  const abs = Math.abs(diff);

  if (abs < MINUTE_MS) return justNow(locale);

  const bucket = pickBucket(abs);
  if (!bucket) return justNow(locale);

  const isPast = diff < 0;
  const signedValue = isPast ? -bucket.value : bucket.value;

  const intlResult = tryFormatIntl(signedValue, bucket.unit, locale);
  if (intlResult !== null) return intlResult;

  return formatManualFallback(bucket, isPast, locale);
}

/**
 * Render a numeric timestamp as an ISO 8601 string for `<time title>`.
 *
 * TOTAL: returns `""` for `NaN` / `Infinity` / out-of-range values that
 * would cause `Date#toISOString` to throw.
 */
export function formatLocalIso(ms: number): string {
  if (!Number.isFinite(ms)) return "";
  try {
    return new Date(ms).toISOString();
  } catch {
    return "";
  }
}
