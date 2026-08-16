import { useState } from "react";
import { Loader2, Building2 } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { ProviderSelector } from "./ProviderSelector";

export interface SamlProvider {
  id: string;
  name: string;
  enabled: boolean;
}

interface SSOLoginButtonProps {
  providers: SamlProvider[];
  onInitiateSSO: (providerId: string) => Promise<void>;
  disabled?: boolean;
}

export function SSOLoginButton({ providers, onInitiateSSO, disabled = false }: SSOLoginButtonProps) {
  const [showProviderSelector, setShowProviderSelector] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>("");

  const enabledProviders = providers.filter((provider) => provider.enabled);

  if (enabledProviders.length === 0) {
    return null;
  }

  async function handleSSOClick() {
    if (enabledProviders.length === 1) {
      await handleProviderSelect(enabledProviders[0].id);
    } else {
      setShowProviderSelector(true);
    }
  }

  async function handleProviderSelect(providerId: string) {
    setPending(true);
    setError("");
    setShowProviderSelector(false);

    try {
      await onInitiateSSO(providerId);
    } catch (initiateError) {
      setError(initiateError instanceof Error ? initiateError.message : "SSO 登录失败");
      setPending(false);
    }
  }

  function handleCancelSelection() {
    setShowProviderSelector(false);
    setError("");
  }

  if (showProviderSelector) {
    return (
      <div className="space-y-2">
        <ProviderSelector
          providers={enabledProviders}
          onSelect={handleProviderSelect}
          onCancel={handleCancelSelection}
        />
        {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="primary"
        className="w-full"
        disabled={disabled || pending}
        onClick={() => void handleSSOClick()}
      >
        {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Building2 className="h-3.5 w-3.5" />}
        使用 SSO 登录
      </Button>
      {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}
    </div>
  );
}
