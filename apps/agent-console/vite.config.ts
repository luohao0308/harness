import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiProxyTarget = process.env.HARNESS_API_PROXY_TARGET ?? "http://127.0.0.1:8000";
const featureChunkByPath: Array<[string, string]> = [
  ["feature-workspace", "/src/features/agents/"],
  ["feature-workspace", "/src/features/teams/"],
  ["feature-workspace", "/src/features/observability/"],
  ["feature-workspace", "/src/features/evals/"],
  ["feature-subagents", "/src/features/subagents/"],
  ["feature-tools", "/src/features/tools/"],
];

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalized = id.replace(/\\/g, "/");
          if (normalized.includes("/node_modules/")) {
            if (
              normalized.includes("/react/") ||
              normalized.includes("/react-dom/") ||
              normalized.includes("/react-router-dom/")
            ) {
              return "vendor-react";
            }
            if (normalized.includes("/@tanstack/react-query/")) {
              return "vendor-tanstack";
            }
            if (normalized.includes("/echarts/") || normalized.includes("/zrender/")) {
              return "vendor-echarts";
            }
            if (normalized.includes("/lucide-react/")) {
              return "vendor-lucide";
            }
          }
          const featureChunk = featureChunkByPath.find(([, featurePath]) =>
            normalized.includes(featurePath),
          );
          return featureChunk?.[0];
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/health": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/metrics": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
