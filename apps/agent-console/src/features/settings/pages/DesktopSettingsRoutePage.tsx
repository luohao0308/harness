import { isDesktopRuntime } from "../../../lib/desktop-bridge";
import { AdvancedFeaturesPage } from "./AdvancedFeaturesPage";
import { DesktopSettingsPage } from "./DesktopSettingsPage";

export function DesktopSettingsRoutePage() {
  return isDesktopRuntime() ? <DesktopSettingsPage /> : <AdvancedFeaturesPage />;
}
