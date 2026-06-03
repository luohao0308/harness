import { createFrontendError } from "../features/tasks/api";

type ReportInput = {
  error: unknown;
  source: string;
  metadata?: Record<string, unknown>;
};

type BufferedError = {
  error_message: string;
  stack: string | null;
  url: string;
  browser: string;
  metadata_json: Record<string, unknown>;
};

const FLUSH_DELAY_MS = 5_000;
const MAX_BATCH_SIZE = 5;

let installed = false;
let flushTimer: number | null = null;
let buffer: BufferedError[] = [];

export function installGlobalErrorReporter() {
  if (installed || typeof window === "undefined") return;
  installed = true;

  window.addEventListener("error", (event) => {
    reportFrontendError({
      error: event.error ?? event.message,
      source: "window.error",
      metadata: {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      },
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    reportFrontendError({
      error: event.reason,
      source: "window.unhandledrejection",
    });
  });
}

export function reportFrontendError(input: ReportInput) {
  if (typeof window === "undefined") return;
  buffer.push(toBufferedError(input));
  if (buffer.length >= MAX_BATCH_SIZE) {
    void flushFrontendErrors();
    return;
  }
  if (flushTimer !== null) return;
  flushTimer = window.setTimeout(() => {
    void flushFrontendErrors();
  }, FLUSH_DELAY_MS);
}

export async function flushFrontendErrors() {
  if (flushTimer !== null) {
    window.clearTimeout(flushTimer);
    flushTimer = null;
  }
  const pending = buffer.splice(0, MAX_BATCH_SIZE);
  for (const item of pending) {
    try {
      await createFrontendError(item);
    } catch {
      // Error reporting must never create a secondary user-facing failure loop.
    }
  }
  if (buffer.length > 0) {
    flushTimer = window.setTimeout(() => {
      void flushFrontendErrors();
    }, FLUSH_DELAY_MS);
  }
}

function toBufferedError({ error, source, metadata }: ReportInput): BufferedError {
  const errorObject = error instanceof Error ? error : null;
  const message = errorObject?.message || stringifyError(error);
  return {
    error_message: message.slice(0, 4000),
    stack: errorObject?.stack?.slice(0, 12000) ?? null,
    url: window.location.href,
    browser: navigator.userAgent,
    metadata_json: {
      source,
      ...metadata,
    },
  };
}

function stringifyError(error: unknown) {
  if (typeof error === "string") return error;
  if (error === null || error === undefined) return "Unknown frontend error";
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}
