import { isRouteErrorResponse, useRouteError } from "react-router-dom";

import { localizeError } from "../lib/error-localization";
import { reportFrontendError } from "../lib/error-reporter";
import { Button } from "./ui/button";

export function RouteErrorBoundary() {
  const error = useRouteError();
  const routeError = isRouteErrorResponse(error)
    ? new Error(`${error.status} ${error.statusText}`)
    : error instanceof Error
      ? error
      : new Error("未知路由错误");
  const localized = localizeError(routeError, "当前页面加载失败，请返回首页或刷新页面");

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-slate-900">
      <div className="w-full max-w-lg rounded-lg border border-slate-200 bg-white p-5 shadow-panel">
        <div className="text-base font-semibold">控制台出现异常</div>
        <div className="mt-1 text-xs text-slate-400">控制台路由错误</div>
        <p className="mt-3 rounded-md bg-slate-50 p-3 text-sm text-slate-600">
          {localized.message}
        </p>
        <details className="mt-3 rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-500">
          <summary className="cursor-pointer font-medium text-slate-700">查看技术详情</summary>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words">
            {localized.technicalDetail ?? routeError.message}
          </pre>
        </details>
        <div className="mt-4 flex gap-2">
          <a href="/">
            <Button variant="primary">返回首页</Button>
          </a>
          <Button onClick={() => window.location.reload()}>刷新页面</Button>
          <Button
            onClick={() =>
              reportFrontendError({ error: routeError, source: "react-router.error-element" })
            }
          >
            上报问题
          </Button>
        </div>
      </div>
    </div>
  );
}
