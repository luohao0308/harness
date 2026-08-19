import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Forge Harness | Enterprise AI Control Plane",
  description: "Forge Harness 是面向企业私有部署的 AI 控制面，提供模型、知识、工具、策略、评测和可观测运行能力。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
