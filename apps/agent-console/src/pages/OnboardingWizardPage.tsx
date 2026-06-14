import { useState } from "react";

import { WelcomeStep, WizardLayout, WizardStep } from "../components/onboarding";

const ONBOARDING_STEPS: WizardStep[] = [
  { id: "welcome", title: "Welcome", description: "Get started" },
  { id: "profile", title: "Profile", description: "Setup your profile" },
  { id: "preferences", title: "Preferences", description: "Choose your preferences" },
  { id: "team", title: "Team", description: "Invite team members" },
  { id: "integrations", title: "Integrations", description: "Connect services" },
  { id: "review", title: "Review", description: "Review your settings" },
  { id: "complete", title: "Complete", description: "Finish setup" },
];

export function OnboardingWizardPage() {
  const [currentStep, setCurrentStep] = useState(0);

  const handleNext = () => {
    if (currentStep < ONBOARDING_STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSkip = () => {
    // Navigate to dashboard or skip onboarding
    console.log("Skipping onboarding");
  };

  const handleGetStarted = () => {
    handleNext();
  };

  return (
    <WizardLayout
      steps={ONBOARDING_STEPS}
      currentStep={currentStep}
      onNext={handleNext}
      onPrevious={handlePrevious}
      onSkip={handleSkip}
      nextLabel={currentStep === 0 ? "Get Started" : "Next"}
    >
      {currentStep === 0 && <WelcomeStep onGetStarted={handleGetStarted} />}
      {currentStep === 1 && <div>Profile Step - Coming Soon</div>}
      {currentStep === 2 && <div>Preferences Step - Coming Soon</div>}
      {currentStep === 3 && <div>Team Step - Coming Soon</div>}
      {currentStep === 4 && <div>Integrations Step - Coming Soon</div>}
      {currentStep === 5 && <div>Review Step - Coming Soon</div>}
      {currentStep === 6 && <div>Complete Step - Coming Soon</div>}
    </WizardLayout>
  );
}
