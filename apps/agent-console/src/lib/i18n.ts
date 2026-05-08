import { useConsoleStore } from "../stores/consoleStore";

export function useI18n() {
  const locale = useConsoleStore((state) => state.locale);
  const isChinese = locale === "zh-CN";

  return {
    locale,
    isChinese,
    text: (zh: string, en: string) => (isChinese ? zh : en),
  };
}
