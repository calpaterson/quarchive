import { getClientID } from "./quarchive-config.js"
import {
    SyncResult,
    SyncStatus,
    fullSync,
    getLastFullSyncResult,
    openIDB,
    registerLastFullSyncResultChangeHandler,
} from "./quarchive-sync.js"

function flash(message: string){
    const note_elem = document.querySelector("#test-or-save-note");
    note_elem.textContent = message;
}

function clearFlash() {
    const note_elem = document.querySelector("#test-or-save-note");
    note_elem.textContent = "";
}

async function saveOptions(e){
    clearFlash();
    let APIURLInput = document.querySelector("#api-url") as HTMLInputElement;
    let usernameInput = document.querySelector("#username") as HTMLInputElement;
    let APIKeyInput = document.querySelector("#api-key") as HTMLInputElement;

    browser.storage.sync.set({
        APIURL: APIURLInput.value,
        username: usernameInput.value,
        APIKey: APIKeyInput.value,
    }).then(
        async function() {
            flash("Saved!");
            await openIDB();
            await fullSync();
        },
        function(error_message) {
            console.error("unable to save preferences! %o", error_message);
            flash("error saving preferences!");
        }
    );
    e.preventDefault()
}

async function testOptions(e): Promise<void> {
    clearFlash();
    let APIURLInput = document.querySelector("#api-url") as HTMLInputElement;
    let usernameInput = document.querySelector("#username") as HTMLInputElement;
    let APIKeyInput = document.querySelector("#api-key") as HTMLInputElement;

    const url = new URL("/api/sync/check-api-key", APIURLInput.value).toString();
    const username = usernameInput.value;
    const APIKey = APIKeyInput.value;
    const extensionVersion = browser.runtime.getManifest().version;
    const clientID = await getClientID();

    await fetch(url, {
        method: "POST",
        headers: {
            "Quarchive-Extension-Version": extensionVersion,
            "Quarchive-Username": username,
            "Quarchive-API-Key": APIKey,
            "Quarchive-ClientID": clientID,
        }
    }).then(
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
        },
        function(reason){
            console.error("network level error trying to test credentials");
            flash("network level error");
        }
    );
    e.preventDefault()
}

async function restoreOptions(){
    var gettingUsername = browser.storage.sync.get("username");
    gettingUsername.then(function (result) {
        let input = document.querySelector("#username") as HTMLInputElement;
        if (result.username !== undefined) {
            input.value = result.username;
        }
    })

    var gettingKey = browser.storage.sync.get("APIKey");
    gettingKey.then(function (result) {
        let input = document.querySelector("#api-key") as HTMLInputElement;
        if (result.APIKey !== undefined) {
            input.value = result.APIKey;
        }
    })

    var gettingURL = browser.storage.sync.get("APIURL");
    gettingURL.then(function (result) {
        let input = document.querySelector("#api-url") as HTMLInputElement;
        if (result.APIURL === undefined) {
            input.value = "https://quarchive.com"
        } else {
            input.value = result.APIURL;
        }
    })

    const [clientID, lastFullSyncResult] = await Promise.all([getClientID(), getLastFullSyncResult()])

    const clientIDSpan = document.querySelector("#client-id") as HTMLElement
    clientIDSpan.textContent = clientID
    updateLastSync(lastFullSyncResult);
}

function updateLastSync(result: SyncResult): void {
    const lastSyncSpan = document.querySelector("#last-full-sync") as HTMLElement
    if (result.status === SyncStatus.Never){
        lastSyncSpan.textContent = "Never done one before";
    } else if (result.status === SyncStatus.InProgress) {
        lastSyncSpan.textContent = `In progress since ${result.at.toLocaleString()}`;
    } else if (result.status === SyncStatus.Failed) {
        lastSyncSpan.textContent = `Failed at ${result.at.toLocaleString()}`;
    } else {
        lastSyncSpan.textContent = `Completed successfully at ${result.at.toLocaleString()}`;
    }
}

async function forceFullSync(): Promise<void> {
    await openIDB();
    await fullSync(true);
}

document.addEventListener('DOMContentLoaded', restoreOptions);
document.addEventListener('DOMContentLoaded', async function(){
    await registerLastFullSyncResultChangeHandler(updateLastSync);
});
document.querySelector("form").addEventListener("submit", saveOptions);
document.querySelector("#force-sync").addEventListener("click", forceFullSync);
document.querySelector("#test-preferences").addEventListener("click", testOptions);
