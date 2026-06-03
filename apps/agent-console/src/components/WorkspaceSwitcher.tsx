import { Building2, Check, Loader2 } from "lucide-react";
import { useState } from "react";

import { Button } from "./ui/button";
import { MenuSelect } from "./ui/menu-select";
import { useOptionalAuth } from "../features/auth/AuthProvider";

export function WorkspaceSwitcher() {
  const auth = useOptionalAuth();
  const currentOrganization = auth?.currentOrganization ?? null;
  const isUsingDevToken = auth?.isUsingDevToken ?? true;
  const switchOrganization = auth?.switchOrganization;
  const user = auth?.user ?? null;
  const [pendingOrgId, setPendingOrgId] = useState<string | null>(null);
  const organizations = user?.organizations ?? [];

  if (!currentOrganization) {
    return (
      <Button className="hidden max-w-48 truncate md:inline-flex" disabled>
        <Building2 className="h-3.5 w-3.5" />
        工作区
      </Button>
    );
  }

  if (organizations.length <= 1) {
    return (
      <Button className="hidden max-w-56 truncate md:inline-flex" title={currentOrganization.name}>
        <Building2 className="h-3.5 w-3.5" />
        <span className="truncate">{currentOrganization.name}</span>
      </Button>
    );
  }

  return (
    <MenuSelect
      ariaLabel="切换工作区"
      className="hidden w-56 md:block"
      size="compact"
      value={currentOrganization.id}
      onChange={(organizationId) => {
        if (!switchOrganization) return;
        setPendingOrgId(organizationId);
        void switchOrganization(organizationId).finally(() => setPendingOrgId(null));
      }}
      disabled={isUsingDevToken}
      leading={
        pendingOrgId ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Building2 className="h-3.5 w-3.5" />
        )
      }
      options={organizations.map((organization) => ({
        value: organization.id,
        label: organization.name,
        description: isUsingDevToken ? "dev-token 会话" : organization.slug,
        meta: organization.role,
        leading: organization.id === currentOrganization.id ? <Check className="h-4 w-4" /> : null,
      }))}
      buttonClassName="rounded-md shadow-none"
      menuClassName="w-64"
    />
  );
}
