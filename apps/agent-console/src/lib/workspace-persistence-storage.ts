export type WorkspacePersistenceStorage = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => unknown;
  removeItem: (key: string) => unknown;
};

export function getWorkspacePersistenceStorage(): WorkspacePersistenceStorage | null {
  if (typeof window !== "undefined") {
    const desktopStorage = window.desktopApi?.storage;
    if (desktopStorage) return desktopStorage;
  }
  return typeof localStorage === "undefined" ? null : localStorage;
}
