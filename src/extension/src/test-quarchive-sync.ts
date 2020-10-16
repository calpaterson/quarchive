import './browser.mock'
import {getLastFullSyncStatus, SyncResult, SyncStatus} from './quarchive-sync'

describe("sync statuses", function(){
    test("getting the last sync status when there's never been one before", async function(){
        await browser.storage.sync.clear();
        const lastFullSyncStatus = await getLastFullSyncStatus();

        const expected = {"status": SyncStatus.Never, "at": new Date("1970-01-01T00:00:00Z")};
        expect(lastFullSyncStatus).toMatchObject(expected);
    });
});
