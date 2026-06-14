import { Bot, Gauge, Network, Shield, Zap } from "lucide-react";

export interface WelcomeStepProps {
  onGetStarted: () => void;
}

interface Feature {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}

const features: Feature[] = [
  {
    icon: Network,
    title: "Multi-Agent Orchestration",
    description: "Coordinate specialized agents to work together seamlessly on complex tasks",
  },
  {
    icon: Zap,
    title: "Intelligent Task Routing",
    description: "Automatically route work to the most appropriate agent based on expertise",
  },
  {
    icon: Gauge,
    title: "Real-Time Monitoring",
    description: "Track agent performance, task progress, and system health in real-time",
  },
  {
    icon: Shield,
    title: "Enterprise Security",
    description: "Built-in security controls, audit logs, and compliance features",
  },
  {
    icon: Bot,
    title: "Extensible Agent System",
    description: "Create custom agents tailored to your specific workflows and requirements",
  },
];

export function WelcomeStep({ onGetStarted }: WelcomeStepProps) {
  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <div className="text-center">
        <div className="mb-6 flex justify-center">
          <div className="rounded-full bg-blue-100 p-6">
            <Bot className="h-16 w-16 text-blue-600" />
          </div>
        </div>
        <h1 className="mb-4 text-3xl font-bold text-slate-900 sm:text-4xl">
          Welcome to Agent Console
        </h1>
        <p className="mx-auto max-w-2xl text-lg text-slate-600">
          Your intelligent multi-agent orchestration platform. Let's get you set up in just a few
          steps.
        </p>
      </div>

      {/* Product Highlights */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((feature) => {
          const Icon = feature.icon;
          return (
            <div
              key={feature.title}
              className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50">
                <Icon className="h-6 w-6 text-blue-600" />
              </div>
              <h3 className="mb-2 text-lg font-semibold text-slate-900">{feature.title}</h3>
              <p className="text-sm text-slate-600">{feature.description}</p>
            </div>
          );
        })}
      </div>

      {/* Get Started Button */}
      <div className="flex justify-center pt-4">
        <button
          onClick={onGetStarted}
          className="rounded-lg bg-blue-600 px-8 py-3 text-base font-medium text-white shadow-sm transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          type="button"
        >
          Get Started
        </button>
      </div>
    </div>
  );
}
