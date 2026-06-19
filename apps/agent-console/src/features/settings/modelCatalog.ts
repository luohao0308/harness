export type ProviderConfig = {
  name: string;
  label?: string;
  provider_id?: string;
  catalog_provider?: string;
  catalog_model?: string;
  secret_provider?: string;
  enabled?: boolean;
  is_custom?: boolean;
  model?: string;
  status?: string;
  api_format?: string;
  base_url?: string;
  api_key?: string;
  api_key_env?: string;
  api_key_configured?: boolean;
  api_key_source?: string;
  api_key_secret_id?: string | null;
  model_kind?: string;
  model_context_window_tokens?: number;
  max_output_tokens?: number;
  rate_limit_rpm?: number;
  rate_limit_tpm?: number;
  timeout_seconds?: number;
  health_timeout_seconds?: number;
  circuit_breaker?: {
    failure_threshold?: number;
    cooldown_seconds?: number;
  };
  [key: string]: unknown;
};

export type ModelCatalogModel = {
  model: string;
  label: string;
  model_kind: string;
  model_context_window_tokens?: number;
  max_output_tokens?: number;
  rate_limit_rpm?: number;
  rate_limit_tpm?: number;
  timeout_seconds?: number;
  health_timeout_seconds?: number;
};

export type ModelCatalogProvider = {
  providerId: string;
  label: string;
  vendorKey: string;
  apiFormat: string;
  baseUrl: string;
  apiKeyEnv: string;
  secretProvider: string;
  isLocal?: boolean;
  models: ModelCatalogModel[];
};

export type ProviderGroup = {
  key: string;
  label: string;
  providers: ProviderConfig[];
};

export type SwitchboardModelRow = {
  catalogProvider: ModelCatalogProvider;
  provider: ProviderConfig;
  configuredProvider: ProviderConfig | null;
  isConfigured: boolean;
  canSwitch: boolean;
  isDefault: boolean;
  isCatalogModel: boolean;
};

const deepSeekProviderBase = {
  apiFormat: "openai",
  baseUrl: "https://api.deepseek.com",
  apiKeyEnv: "DEEPSEEK_API_KEY",
  secretProvider: "deepseek",
  model_context_window_tokens: 1000000,
  max_output_tokens: 384000,
  rate_limit_rpm: 300,
  rate_limit_tpm: 1000000,
  timeout_seconds: 60,
  health_timeout_seconds: 5,
};

export const modelCatalog: ModelCatalogProvider[] = [
  {
    providerId: "deepseek",
    label: "DeepSeek",
    vendorKey: "deepseek",
    ...deepSeekProviderBase,
    models: [
      {
        model: "deepseek-v4-flash",
        label: "DeepSeek Flash",
        model_kind: "文本模型",
        model_context_window_tokens: deepSeekProviderBase.model_context_window_tokens,
        max_output_tokens: deepSeekProviderBase.max_output_tokens,
        rate_limit_rpm: deepSeekProviderBase.rate_limit_rpm,
        rate_limit_tpm: deepSeekProviderBase.rate_limit_tpm,
        timeout_seconds: deepSeekProviderBase.timeout_seconds,
        health_timeout_seconds: deepSeekProviderBase.health_timeout_seconds,
      },
      {
        model: "deepseek-v4-pro",
        label: "DeepSeek Pro",
        model_kind: "推理模型",
        model_context_window_tokens: deepSeekProviderBase.model_context_window_tokens,
        max_output_tokens: deepSeekProviderBase.max_output_tokens,
        rate_limit_rpm: deepSeekProviderBase.rate_limit_rpm,
        rate_limit_tpm: deepSeekProviderBase.rate_limit_tpm,
        timeout_seconds: deepSeekProviderBase.timeout_seconds,
        health_timeout_seconds: deepSeekProviderBase.health_timeout_seconds,
      },
    ],
  },
  {
    providerId: "openai",
    label: "OpenAI",
    vendorKey: "openai",
    apiFormat: "openai",
    baseUrl: "https://api.openai.com/v1",
    apiKeyEnv: "OPENAI_API_KEY",
    secretProvider: "openai",
    models: [
      {
        model: "gpt-5.5",
        label: "OpenAI GPT-5.5",
        model_kind: "推理模型",
        model_context_window_tokens: 272000,
        max_output_tokens: 128000,
        rate_limit_rpm: 600,
        rate_limit_tpm: 120000,
        timeout_seconds: 30,
        health_timeout_seconds: 5,
      },
      {
        model: "gpt-5.3-codex-spark",
        label: "OpenAI GPT-5.3 Codex Spark",
        model_kind: "文本模型",
        model_context_window_tokens: 272000,
        max_output_tokens: 128000,
        rate_limit_rpm: 600,
        rate_limit_tpm: 120000,
        timeout_seconds: 30,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "anthropic",
    label: "Anthropic",
    vendorKey: "anthropic",
    apiFormat: "anthropic",
    baseUrl: "https://api.anthropic.com",
    apiKeyEnv: "ANTHROPIC_API_KEY",
    secretProvider: "anthropic",
    models: [
      {
        model: "claude-opus-4.5",
        label: "Claude Opus 4.5",
        model_kind: "推理模型",
        model_context_window_tokens: 200000,
        max_output_tokens: 32000,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 45,
        health_timeout_seconds: 5,
      },
      {
        model: "claude-sonnet-4.5",
        label: "Claude Sonnet 4.5",
        model_kind: "文本模型",
        model_context_window_tokens: 200000,
        max_output_tokens: 32000,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 45,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "gemini",
    label: "Gemini",
    vendorKey: "gemini",
    apiFormat: "openai",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    apiKeyEnv: "GEMINI_API_KEY",
    secretProvider: "gemini",
    models: [
      {
        model: "gemini-2.5-pro",
        label: "Gemini 2.5 Pro",
        model_kind: "推理模型",
        model_context_window_tokens: 1000000,
        max_output_tokens: 65536,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 45,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "kimi",
    label: "Kimi",
    vendorKey: "kimi",
    apiFormat: "openai",
    baseUrl: "https://api.moonshot.cn/v1",
    apiKeyEnv: "MOONSHOT_API_KEY",
    secretProvider: "moonshot",
    models: [
      {
        model: "kimi-k2.6",
        label: "Kimi K2.6",
        model_kind: "推理模型",
        model_context_window_tokens: 262144,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 30,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "z-ai",
    label: "Z.AI",
    vendorKey: "z-ai",
    apiFormat: "openai",
    baseUrl: "https://api.z.ai/api/paas/v4",
    apiKeyEnv: "ZAI_API_KEY",
    secretProvider: "z-ai",
    models: [
      {
        model: "glm-5.1",
        label: "Z.AI GLM-5.1",
        model_kind: "推理模型",
        model_context_window_tokens: 200000,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 30,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "qwen",
    label: "Qwen",
    vendorKey: "qwen",
    apiFormat: "openai",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    apiKeyEnv: "DASHSCOPE_API_KEY",
    secretProvider: "qwen",
    models: [
      {
        model: "qwen-max-latest",
        label: "Qwen Max Latest",
        model_kind: "文本模型",
        model_context_window_tokens: 131072,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 30,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "doubao",
    label: "Doubao",
    vendorKey: "doubao",
    apiFormat: "openai",
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    apiKeyEnv: "ARK_API_KEY",
    secretProvider: "doubao",
    models: [
      {
        model: "doubao-seed-1-6",
        label: "Doubao Seed 1.6",
        model_kind: "文本模型",
        model_context_window_tokens: 256000,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 30,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "openrouter",
    label: "OpenRouter",
    vendorKey: "openrouter",
    apiFormat: "openai",
    baseUrl: "https://openrouter.ai/api/v1",
    apiKeyEnv: "OPENROUTER_API_KEY",
    secretProvider: "openrouter",
    models: [
      {
        model: "openai/gpt-5.5",
        label: "OpenRouter GPT-5.5",
        model_kind: "推理模型",
        model_context_window_tokens: 272000,
        max_output_tokens: 128000,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 45,
        health_timeout_seconds: 5,
      },
      {
        model: "anthropic/claude-sonnet-4.5",
        label: "OpenRouter Claude Sonnet 4.5",
        model_kind: "文本模型",
        model_context_window_tokens: 200000,
        max_output_tokens: 32000,
        rate_limit_rpm: 300,
        rate_limit_tpm: 120000,
        timeout_seconds: 45,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "ollama",
    label: "Ollama / Local",
    vendorKey: "ollama",
    apiFormat: "openai",
    baseUrl: "http://127.0.0.1:11434/v1",
    apiKeyEnv: "",
    secretProvider: "ollama",
    isLocal: true,
    models: [
      {
        model: "llama3.1",
        label: "Llama 3.1",
        model_kind: "文本模型",
        model_context_window_tokens: 128000,
        rate_limit_rpm: 0,
        rate_limit_tpm: 0,
        timeout_seconds: 60,
        health_timeout_seconds: 5,
      },
    ],
  },
  {
    providerId: "custom",
    label: "自定义",
    vendorKey: "custom",
    apiFormat: "openai",
    baseUrl: "",
    apiKeyEnv: "",
    secretProvider: "custom",
    models: [],
  },
];

export const emptyProvider: ProviderConfig = {
  name: "custom-openai-compatible",
  label: "自定义 OpenAI 兼容",
  provider_id: "custom",
  catalog_provider: "custom",
  secret_provider: "custom-openai-compatible",
  model: "default",
  catalog_model: "default",
  api_format: "openai",
  base_url: "",
  api_key: "",
  api_key_env: "",
  model_context_window_tokens: 0,
  rate_limit_rpm: 300,
  rate_limit_tpm: 120000,
  timeout_seconds: 30,
  health_timeout_seconds: 5,
  circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
  is_custom: true,
  enabled: true,
};

export function flattenModelCatalog(catalog = modelCatalog): ProviderConfig[] {
  return catalog.flatMap((catalogProvider) =>
    catalogProvider.models.map((model) =>
      catalogProviderModelToProvider(catalogProvider, model),
    ),
  );
}

export function catalogProviderModelToProvider(
  catalogProvider: ModelCatalogProvider,
  model: ModelCatalogModel,
): ProviderConfig {
  const fallbackName =
    catalogProvider.models.length === 1
      ? catalogProvider.providerId
      : `${catalogProvider.providerId}-${slugModelId(model.model)}`;
  const legacyName = legacyProviderName(catalogProvider.providerId, model.model);
  return {
    name: legacyName ?? fallbackName,
    label: model.label,
    provider_id: catalogProvider.providerId,
    catalog_provider: catalogProvider.providerId,
    catalog_model: model.model,
    secret_provider: catalogProvider.secretProvider,
    model: model.model,
    model_kind: model.model_kind,
    api_format: catalogProvider.apiFormat,
    base_url: catalogProvider.baseUrl,
    api_key: "",
    api_key_env: catalogProvider.apiKeyEnv,
    model_context_window_tokens: model.model_context_window_tokens,
    max_output_tokens: model.max_output_tokens,
    rate_limit_rpm: model.rate_limit_rpm,
    rate_limit_tpm: model.rate_limit_tpm,
    timeout_seconds: model.timeout_seconds,
    health_timeout_seconds: model.health_timeout_seconds,
    status: "healthy",
    enabled: true,
    is_custom: false,
    circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
  };
}

export function mergePresetAndConfiguredProviders(configuredProviders: ProviderConfig[]) {
  const merged = new Map<string, ProviderConfig>();
  for (const preset of flattenModelCatalog()) {
    const configured = configuredProviders.find((provider) => providerKey(provider) === providerKey(preset));
    merged.set(providerKey(preset), configured ? { ...preset, ...configured } : preset);
  }
  for (const provider of configuredProviders) {
    if (!merged.has(providerKey(provider))) {
      merged.set(providerKey(provider), provider);
    }
  }
  return Array.from(merged.values());
}

export function buildSwitchboardRows(
  configuredProviders: ProviderConfig[],
  currentDefault: { provider?: string; model?: string },
) {
  return modelCatalog.flatMap((catalogProvider) => {
    const catalogRows = catalogProvider.models.map((model) => {
      const provider = catalogProviderModelToProvider(catalogProvider, model);
      const configuredProvider = configuredProviders.find((item) => providerKey(item) === providerKey(provider)) ?? null;
      const displayProvider = configuredProvider ? { ...provider, ...configuredProvider } : provider;
      const sharedSecretProvider = findConfiguredProviderForModel(displayProvider, configuredProviders);
      const isDefault =
        currentDefault.provider === displayProvider.name &&
        currentDefault.model === String(displayProvider.model ?? "default");
      return {
        catalogProvider,
        provider: displayProvider,
        configuredProvider: sharedSecretProvider,
        isConfigured: Boolean(sharedSecretProvider),
        canSwitch: Boolean(sharedSecretProvider) || Boolean(catalogProvider.isLocal),
        isDefault,
        isCatalogModel: true,
      } satisfies SwitchboardModelRow;
    });
    const configuredOnlyRows = configuredProviders
      .filter((provider) =>
        catalogProvider.providerId === "custom"
          ? isCustomProvider(provider)
          : providerVendorKey(provider) === catalogProvider.vendorKey,
      )
      .filter(
        (provider) =>
          !catalogRows.some((row) => providerKey(row.provider) === providerKey(provider)),
      )
      .map((provider) => {
        const sharedSecretProvider = findConfiguredProviderForModel(provider, configuredProviders);
        return {
          catalogProvider,
          provider,
          configuredProvider: sharedSecretProvider,
          isConfigured: Boolean(sharedSecretProvider),
          canSwitch: Boolean(sharedSecretProvider) || Boolean(catalogProvider.isLocal),
          isDefault:
            currentDefault.provider === provider.name &&
            currentDefault.model === String(provider.model ?? "default"),
          isCatalogModel: false,
        } satisfies SwitchboardModelRow;
      });
    return [...catalogRows, ...configuredOnlyRows];
  });
}

export function providerHasUsableApiKey(provider: ProviderConfig) {
  if (provider.api_key_configured === true) {
    return true;
  }
  const apiKey = String(provider.api_key ?? "").trim();
  return apiKey.length > 0 && apiKey !== "replace-me";
}

export function findConfiguredProviderForModel(
  provider: ProviderConfig,
  providers: ProviderConfig[],
): ProviderConfig | null {
  const exactProvider = providers.find((item) => providerKey(item) === providerKey(provider));
  if (exactProvider && providerHasUsableApiKey(exactProvider)) {
    return exactProvider;
  }
  const expectedSecretProvider = providerSecretKey(provider);
  return (
    providers.find(
      (item) =>
        providerSecretKey(item) === expectedSecretProvider &&
        providerHasUsableApiKey(item),
    ) ?? null
  );
}

export function providerWithSharedSecret(
  provider: ProviderConfig,
  sharedSecretProvider: ProviderConfig,
): ProviderConfig {
  return {
    ...provider,
    api_key: "",
    api_key_configured: true,
    api_key_source: sharedSecretProvider.api_key_source,
    api_key_secret_id: sharedSecretProvider.api_key_secret_id ?? null,
    secret_provider: providerSecretKey(provider),
  };
}

export function providerKey(provider: ProviderConfig) {
  return `${provider.name}:${String(provider.model ?? "default")}`;
}

export function providerSecretKey(provider: ProviderConfig) {
  const explicit = String(provider.secret_provider ?? "").trim().toLowerCase();
  if (explicit) return explicit;
  return providerVendorKey(provider);
}

export function providerVendorKey(provider: ProviderConfig) {
  const explicit = String(provider.provider_id ?? provider.catalog_provider ?? "").trim().toLowerCase();
  if (explicit && explicit !== "custom") return explicit;
  const name = String(provider.name ?? "").toLowerCase();
  const baseUrl = String(provider.base_url ?? "").toLowerCase();
  if (name.startsWith("deepseek") || baseUrl.includes("deepseek")) return "deepseek";
  if (name.startsWith("openai") || baseUrl.includes("openai.com")) return "openai";
  if (name.startsWith("anthropic") || baseUrl.includes("anthropic")) return "anthropic";
  if (name.startsWith("gemini") || baseUrl.includes("generativelanguage.googleapis.com")) return "gemini";
  if (name.startsWith("kimi") || name.includes("moonshot") || baseUrl.includes("moonshot")) return "kimi";
  if (name.startsWith("z-ai") || name.startsWith("zai") || baseUrl.includes("z.ai")) return "z-ai";
  if (name.startsWith("qwen") || baseUrl.includes("dashscope")) return "qwen";
  if (name.startsWith("doubao") || baseUrl.includes("volces")) return "doubao";
  if (name.startsWith("openrouter") || baseUrl.includes("openrouter")) return "openrouter";
  if (name.startsWith("ollama") || baseUrl.includes("11434")) return "ollama";
  return String(provider.name || provider.label || "custom-provider").trim().toLowerCase();
}

export function vendorDisplayName(provider: ProviderConfig) {
  const labels: Record<string, string> = Object.fromEntries(
    modelCatalog.map((providerItem) => [providerItem.vendorKey, providerItem.label]),
  );
  return labels[providerVendorKey(provider)] ?? String(provider.label || provider.name || "自定义供应商");
}

export function groupProvidersByVendor(providers: ProviderConfig[]): ProviderGroup[] {
  const groups = new Map<string, ProviderGroup>();
  for (const provider of providers) {
    const key = providerVendorKey(provider);
    const existing = groups.get(key);
    if (existing) {
      existing.providers.push(provider);
      continue;
    }
    groups.set(key, {
      key,
      label: vendorDisplayName(provider),
      providers: [provider],
    });
  }
  return Array.from(groups.values()).map((group) => ({
    ...group,
    providers: [...group.providers].sort((left, right) =>
      String(left.model ?? left.name).localeCompare(String(right.model ?? right.name), "zh-CN"),
    ),
  }));
}

export function providerDisplayName(provider: ProviderConfig) {
  return String(provider.label || provider.model || provider.name);
}

function slugModelId(model: string) {
  return model
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function legacyProviderName(providerId: string, model: string) {
  if (providerId === "deepseek" && model === "deepseek-v4-flash") return "deepseek-flash";
  if (providerId === "deepseek" && model === "deepseek-v4-pro") return "deepseek-pro";
  if (providerId === "openai" && model === "gpt-5.5") return "openai-compatible";
  if (providerId === "kimi" && model === "kimi-k2.6") return "kimi";
  if (providerId === "z-ai" && model === "glm-5.1") return "z-ai";
  return null;
}

function isCustomProvider(provider: ProviderConfig) {
  return (
    provider.is_custom === true ||
    String(provider.provider_id ?? "").trim().toLowerCase() === "custom" ||
    String(provider.catalog_provider ?? "").trim().toLowerCase() === "custom"
  );
}
