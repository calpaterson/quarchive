import { getClientID } from "./quarchive-config.js"
import {
    SyncResult,
    SyncStatus,
    fullSync,
    getLastFullSyncResult,
    openIDB,
    registerLastFullSyncResultChangeHandler,
} from "./quarchive-sync.js"

function flash(message: string): void {
    const note_elem = document.querySelector("#test-or-save-note");
    note_elem.textContent = message;
}

function clearFlash() : void {
    const note_elem = document.querySelector("#test-or-save-note");
    note_elem.textContent = "";
}

function saveOptions(e) : void {
    clearFlash();
    let APIURLInput = document.querySelector("#api-url") as HTMLInputElement;
    let usernameInput = document.querySelector("#username") as HTMLInputElement;
    let APIKeyInput = document.querySelector("#api-key") as HTMLInputElement;

    browser.storage.sync.set({
        APIURL: APIURLInput.value,
        username: usernameInput.value,
        APIKey: APIKeyInput.value,
    })
        .then(async function() {
            flash("Saved!");
            await openIDB();
            await fullSync();
        })
        .catch(function(error_message) {
            console.error("unable to save preferences! %o", error_message);
            flash("error saving preferences!");
        });
    e.preventDefault()
}

function testOptions(e): void {
    clearFlash();
    let APIURLInput = document.querySelector("#api-url") as HTMLInputElement;
    let usernameInput = document.querySelector("#username") as HTMLInputElement;
    let APIKeyInput = document.querySelector("#api-key") as HTMLInputElement;

    const url = new URL("/api/sync/check-api-key", APIURLInput.value).toString();
    const username = usernameInput.value;
    const APIKey = APIKeyInput.value;
    const extensionVersion = browser.runtime.getManifest().version;

    async function testOptionsInner(clientID) {
        fetch(url, {
            method: "POST",
            headers: {
                "Quarchive-Extension-Version": extensionVersion,
                "Quarchive-Username": username,
                "Quarchive-API-Key": APIKey,
                "Quarchive-ClientID": clientID,
            }
        })
            .then(
                async function(response){
                    if (response.ok){
                        flash("Tested successfully!");
                    } else {
                        // FIXME: handle bad json returned
                        await response.json().then(
                            function(json){
                                flash(json.error);
                            },
                            function(reason){
                                flash("unreadable response from api");
                            })
                    }
                })
            .catch(
                function(reason){
                    console.error("network level error trying to test credentials");
                    flash("network level error");
                }
            );
    };

    getClientID()
        .catch(function (error) {
            console.error("unable to get clientID: %o", error);
        })
        .then(testOptionsInner)
    e.preventDefault()
}

function restoreOptions(){
    async function restoreOptionsInner() {
        const gettingUsername = browser.storage.sync.get("username");
        gettingUsername.then(function (result) {
            let input = document.querySelector("#username") as HTMLInputElement;
            if (result.username !== undefined) {
                input.value = result.username;
            }
        })

        const gettingKey = browser.storage.sync.get("APIKey");
        gettingKey.then(function (result) {
            let input = document.querySelector("#api-key") as HTMLInputElement;
            if (result.APIKey !== undefined) {
                input.value = result.APIKey;
            }
        })

        const gettingURL = browser.storage.sync.get("APIURL");
        gettingURL.then(function (result) {
        let input = document.querySelector("#api-url") as HTMLInputElement;
            if (result.APIURL === undefined) {
                input.value = "https://quarchive.com"
            } else {
                input.value = result.APIURL;
            }
        })
        await Promise.all([
            gettingUsername,
            gettingKey,
            gettingURL,
        ]);

        const [clientID, lastFullSyncResult] = await Promise.all([
            getClientID(),
            getLastFullSyncResult(),
        ]);

        const clientIDSpan = document.querySelector("#client-id-input") as HTMLInputElement
        clientIDSpan.value = clientID
        updateLastSync(lastFullSyncResult);
    }

    restoreOptionsInner()
        .catch(function(error){ console.error("unable to restore options: %o", error)});
}

function updateLastSync(result: SyncResult): void {
    const lastSyncSpan = document.querySelector("#last-full-sync") as HTMLElement;
    const forceSyncButton = document.querySelector("#force-sync-button") as HTMLButtonElement;
    if (result.status === SyncStatus.Never){
        forceSyncButton.disabled = false;
        lastSyncSpan.textContent = "Never done one before";
    } else if (result.status === SyncStatus.InProgress) {
        forceSyncButton.disabled = true;
        lastSyncSpan.textContent = `In progress since ${result.at.toLocaleString()}`;
    } else if (result.status === SyncStatus.Failed) {
        forceSyncButton.disabled = false;
        lastSyncSpan.textContent = `Failed at ${result.at.toLocaleString()}`;
    } else {
        forceSyncButton.disabled = false;
        lastSyncSpan.textContent = `Completed successfully at ${result.at.toLocaleString()}`;
    }
}

function forceFullSync(): void {
    openIDB()
        .then(async function() { await fullSync(true)})
        .catch(function(error){ console.error("unable to force full sync: %o", error)});
}

document.addEventListener('DOMContentLoaded', restoreOptions);
document.addEventListener('DOMContentLoaded', function(){
    registerLastFullSyncResultChangeHandler(updateLastSync);
});
document.querySelector("form").addEventListener("submit", saveOptions);
document.querySelector("#force-sync-button").addEventListener("click", forceFullSync);
document.querySelector("#test-preferences").addEventListener("click", testOptions);
