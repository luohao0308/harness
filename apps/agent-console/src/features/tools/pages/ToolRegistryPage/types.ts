export type ToolConfigDialog =
  | "marketplace"
  | "trusted-url"
  | "public-url"
  | "upload"
  | "lifecycle"
  | "test-invoke"
  | null;

export type MarketplaceFilter = "all" | "mcp" | "skill";
export type MarketplaceInstallState = "available" | "staged" | "approved" | "installed";
