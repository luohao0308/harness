import { Component, type ErrorInfo, type ReactNode } from "react";
import { Bug, Home, RefreshCw, Send } from "lucide-react";

import { localizeError } from "../lib/error-localization";
import { reportFrontendError } from "../lib/error-reporter";
import { Button } from "./ui/button";

type ErrorBoundaryProps = {
  children: ReactNode;
  scope?: string;
};

type ErrorBoundaryState = {
  error: Error | null;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    reportFrontendError({
      error,
      source: this.props.scope ?? "react.error-boundary",
      metadata: { componentStack: info.componentStack },
    });
  }

  render() {
    const error = this.state.error;
    if (!error) return this.props.children;

    const localized = localizeError(error, "页面遇到异常，请刷新或返回首页");
    const isDev = import.meta.env.DEV;

    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-slate-900">
        <div className="w-full max-w-xl rounded-lg border border-slate-200 bg-white p-5 shadow-panel">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-red-50 text-red-700">
              <Bug className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-base font-semibold">页面出现异常</div>
              <p className="mt-1 text-sm leading-6 text-slate-600">{localized.message}</p>
            </div>
          </div>
          {isDev && localized.technicalDetail ? (
            <details className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
              <summary className="cursor-pointer font-medium text-slate-700">查看技术详情</summary>
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words">
                {localized.technicalDetail}
              </pre>
            </details>
          ) : null}
          <div className="mt-5 flex flex-wrap gap-2">
            <a href="/">
              <Button variant="primary">
                <Home className="h-3.5 w-3.5" />
                返回首页
              </Button>
            </a>
            <Button onClick={() => window.location.reload()}>
              <RefreshCw className="h-3.5 w-3.5" />
              刷新页面
            </Button>
            <Button
              onClick={() => {
                reportFrontendError({
                  error,
                  source: this.props.scope ?? "react.error-boundary.manual-report",
                });
              }}
            >
              <Send className="h-3.5 w-3.5" />
              上报问题
            </Button>
          </div>
        </div>
      </div>
    );
  }
}
