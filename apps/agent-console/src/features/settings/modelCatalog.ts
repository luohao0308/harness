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
  managed_by_platform?: boolean;
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
  managedByPlatform?: boolean;
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

const ollamaCatalogProvider: ModelCatalogProvider = {
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
};

const customCatalogProvider: ModelCatalogProvider = {
  providerId: "custom",
  label: "自定义",
  vendorKey: "custom",
  apiFormat: "openai",
  baseUrl: "",
  apiKeyEnv: "",
  secretProvider: "custom",
  models: [],
};

const platformManagedModel = (model: string, label: string, model_kind: string): ModelCatalogModel => ({
  model,
  label,
  model_kind,
  rate_limit_rpm: 300,
  rate_limit_tpm: 120000,
  timeout_seconds: 30,
  health_timeout_seconds: 5,
});

export const modelCatalog: ModelCatalogProvider[] = [
  {
    providerId: "chybenzun-openai-compatible",
    label: "平台托管模型",
    vendorKey: "chybenzun-openai-compatible",
    apiFormat: "openai",
    baseUrl: "https://ai.112102.xyz/v1",
    apiKeyEnv: "AI_PROVIDER_API_KEY",
    secretProvider: "chybenzun-openai-compatible",
    managedByPlatform: true,
    models: [
      platformManagedModel("deepseek-v4-flash", "DeepSeek V4 Flash", "文本模型"),
      platformManagedModel("gpt-oss-120b", "GPT OSS 120B", "文本模型"),
      platformManagedModel("mimo-v2.5", "MiMo V2.5", "文本模型"),
      platformManagedModel("minimax-m3", "MiniMax M3", "文本模型"),
      platformManagedModel("nvidia-gpt-oss", "NVIDIA GPT OSS", "文本模型"),
    ],
  },
  ollamaCatalogProvider,
  customCatalogProvider,
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

export function buildRuntimeModelCatalog(
  catalog: ModelCatalogProvider[],
  providers: ProviderConfig[],
): ModelCatalogProvider[] {
  const platform = catalog.find((catalogProvider) => catalogProvider.managedByPlatform === true);
  if (!platform) return catalog;

  const runtimeModels = providers
    .filter((provider) => provider.managed_by_platform === true)
    .reduce<ModelCatalogModel[]>((models, provider) => {
      const model = String(provider.model ?? "").trim();
      if (!model || models.some((item) => item.model === model)) return models;
      const known = platform.models.find((item) => item.model === model);
      models.push(
        known ?? {
          model,
          label: String(provider.label || model),
          model_kind: String(provider.model_kind || "文本模型"),
          model_context_window_tokens: Number(provider.model_context_window_tokens || 0) || undefined,
          max_output_tokens: Number(provider.max_output_tokens || 0) || undefined,
          rate_limit_rpm: Number(provider.rate_limit_rpm || 0) || undefined,
          rate_limit_tpm: Number(provider.rate_limit_tpm || 0) || undefined,
          timeout_seconds: Number(provider.timeout_seconds || 0) || undefined,
          health_timeout_seconds: Number(provider.health_timeout_seconds || 0) || undefined,
        },
      );
      return models;
    }, []);

  return catalog.map((catalogProvider) =>
    catalogProvider.providerId === platform.providerId
      ? {
          ...catalogProvider,
          baseUrl: String(providers.find((provider) => provider.managed_by_platform === true)?.base_url || catalogProvider.baseUrl),
          models: runtimeModels,
        }
      : catalogProvider,
  );
}

export function catalogProviderModelToProvider(
  catalogProvider: ModelCatalogProvider,
  model: ModelCatalogModel,
): ProviderConfig {
  const fallbackName =
    catalogProvider.managedByPlatform || catalogProvider.models.length === 1
      ? catalogProvider.providerId
      : `${catalogProvider.providerId}-${slugModelId(model.model)}`;
  return {
    name: fallbackName,
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
    managed_by_platform: catalogProvider.managedByPlatform === true,
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

export function mergePresetAndConfiguredProviders(
  configuredProviders: ProviderConfig[],
  catalog = modelCatalog,
) {
  const merged = new Map<string, ProviderConfig>();
  for (const preset of flattenModelCatalog(catalog)) {
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
  catalog = modelCatalog,
) {
  return catalog.flatMap((catalogProvider) => {
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
  if (provider.managed_by_platform === true) {
    return provider.api_key_configured === true;
  }
  if (provider.isLocal === true || providerVendorKey(provider) === "ollama") {
    return true;
  }
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

function isCustomProvider(provider: ProviderConfig) {
  return (
    provider.is_custom === true ||
    String(provider.provider_id ?? "").trim().toLowerCase() === "custom" ||
    String(provider.catalog_provider ?? "").trim().toLowerCase() === "custom"
  );
}
