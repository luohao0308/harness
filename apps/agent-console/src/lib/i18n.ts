export function useI18n() {
  return {
    locale: "zh-CN" as const,
    isChinese: true,
    text: (zh: string, _en: string) => zh,
  };
}
