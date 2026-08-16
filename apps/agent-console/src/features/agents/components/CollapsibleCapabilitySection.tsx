import { type ReactNode } from "react";

export interface CapabilityProps {
  icon: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  status: string;
  description: string;
  to?: string;
  disabled?: boolean;
}

interface CollapsibleCapabilitySectionProps {
  coreCapabilities: CapabilityProps[];
  advancedCapabilities: CapabilityProps[];
  StudioCapabilityComponent: React.ComponentType<CapabilityProps>;
}

export function CollapsibleCapabilitySection({
  coreCapabilities,
  advancedCapabilities,
  StudioCapabilityComponent,
}: CollapsibleCapabilitySectionProps) {
  const visibleCapabilities = [...coreCapabilities, ...advancedCapabilities].filter(
    (capability) => !capability.disabled,
  );

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {visibleCapabilities.map((cap, index) => (
        <StudioCapabilityComponent key={index} {...cap} />
      ))}
    </div>
  );
}
