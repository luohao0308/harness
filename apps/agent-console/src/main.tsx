import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { router } from "./app/routes";
import { AuthProvider } from "./features/auth/AuthProvider";
import { installDesktopBridge } from "./lib/desktop-bridge";
import { installGlobalErrorReporter } from "./lib/error-reporter";
import { initializeLocalRuntimeSession } from "./lib/local-runtime";
import { installProjectKnowledgeSync } from "./lib/project-knowledge-sync";
import "./styles.css";

if (typeof window !== "undefined" && window.localStorage.getItem("harness.a11y.high_contrast") === "1") {
  document.documentElement.classList.add("theme-high-contrast");
}

installGlobalErrorReporter();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

void initializeLocalRuntimeSession()
  .then(() => {
    installDesktopBridge(router);
    installProjectKnowledgeSync();
    ReactDOM.createRoot(document.getElementById("root")!).render(
      <React.StrictMode>
        <ErrorBoundary scope="app-root">
          <QueryClientProvider client={queryClient}>
            <AuthProvider>
              <RouterProvider router={router} />
            </AuthProvider>
          </QueryClientProvider>
        </ErrorBoundary>
      </React.StrictMode>,
    );
  })
  .catch((error) => {
    const root = document.getElementById("root");
    if (!root) return;
    const message = error instanceof Error ? error.message : "Local session bootstrap failed";
    ReactDOM.createRoot(root).render(
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <section className="w-full max-w-md rounded-lg border border-red-200 bg-white p-5 shadow-sm">
          <h1 className="text-base font-semibold text-slate-950">Unable to open Web Extension</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">{message}</p>
        </section>
      </main>,
    );
  });
