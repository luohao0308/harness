import { create } from "zustand";

type ConsoleState = {
  environment: string;
  locale: "zh-CN" | "en-US";
  setEnvironment: (environment: string) => void;
  setLocale: (locale: "zh-CN" | "en-US") => void;
};

export const useConsoleStore = create<ConsoleState>((set) => ({
  environment: "production",
  locale: "zh-CN",
  setEnvironment: (environment) => set({ environment }),
  setLocale: (locale) => set({ locale }),
}));
