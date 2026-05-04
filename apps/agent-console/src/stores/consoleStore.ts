import { create } from "zustand";

type ConsoleState = {
  environment: string;
  setEnvironment: (environment: string) => void;
};

export const useConsoleStore = create<ConsoleState>((set) => ({
  environment: "production",
  setEnvironment: (environment) => set({ environment }),
}));
