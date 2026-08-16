# ADR 0005: Use Next.js Website And React Console

## Status

accepted

## Context

The product needs a SEO-friendly marketing site and a dense enterprise console with real-time event streams.

## Decision

The website uses Next.js + TypeScript + Tailwind CSS. The console uses React + Vite + TypeScript + Tailwind CSS, local UI primitives, lucide-react, and ECharts. Historical design references to shadcn/ui are treated as design-system targets, not current implementation dependencies.

## Consequences

- Website routes live under `apps/web-site`.
- Console routes live under `apps/agent-console`.
- Figma is the design source.
- Gemini/H5 output is reference material only.
