import { create } from "zustand";

type ConsoleState = {
  environment: string;
  locale: "zh-CN" | "en-US";
  sidebarNavScrollTop: number;
  setEnvironment: (environment: string) => void;
  setLocale: (locale: "zh-CN" | "en-US") => void;
  setSidebarNavScrollTop: (scrollTop: number) => void;
};

export const useConsoleStore = create<ConsoleState>((set) => ({
  environment: "production",
  locale: "zh-CN",
  sidebarNavScrollTop: 0,
  setEnvironment: (environment) => set({ environment }),
  setLocale: () => set({ locale: "zh-CN" }),
  setSidebarNavScrollTop: (scrollTop) => set({ sidebarNavScrollTop: scrollTop }),
}));
