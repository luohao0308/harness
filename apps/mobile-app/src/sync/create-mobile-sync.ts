import { MobileApiClient } from "./api-client";
import { MobileSyncService } from "./mobile-sync-service";
import {
  openHarnessMobileDatabase,
  SQLiteConflictStore,
  SQLiteOfflineQueue,
  SQLiteSyncMetadataStore,
  SQLiteTaskStore,
} from "./sqlite-store";

export async function createMobileSyncService() {
  const db = await openHarnessMobileDatabase();
  const service = new MobileSyncService(
    new MobileApiClient(),
    new SQLiteTaskStore(db),
    new SQLiteOfflineQueue(db),
    new SQLiteSyncMetadataStore(db),
    new SQLiteConflictStore(db),
  );
  await service.initialize();
  return service;
}
