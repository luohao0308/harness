import { Building2 } from "lucide-react";

import { Button } from "../../../components/ui/button";
import type { SamlProvider } from "./SSOLoginButton";

interface ProviderSelectorProps {
  providers: SamlProvider[];
  onSelect: (providerId: string) => void;
  onCancel: () => void;
}

export function ProviderSelector({ providers, onSelect, onCancel }: ProviderSelectorProps) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-slate-600">选择 SSO 提供商</p>
      <div className="space-y-2">
        {providers.map((provider) => (
          <Button
            key={provider.id}
            type="button"
            variant="secondary"
            className="w-full justify-start"
            onClick={() => onSelect(provider.id)}
          >
            <Building2 className="h-3.5 w-3.5" />
            {provider.name}
          </Button>
        ))}
      </div>
      <Button type="button" variant="ghost" className="w-full" onClick={onCancel}>
        取消
      </Button>
    </div>
  );
}
