"use strict";

import { QuarchiveURL, Bookmark, DisallowedSchemeError } from "./value_objects.js"

const SCHEMA_VERSION = 3;

// An hour
const PERIODIC_FULL_SYNC_INTERVAL_IN_MINUTES = 60;

var db: IDBDatabase;

let listenersEnabled = false;

async function getHTTPConfig(): Promise<Array<string>> {
    var gettingKey = await browser.storage.sync.get("APIKey");
    var gettingUsername = await browser.storage.sync.get("username");
    var gettingURL = await browser.storage.sync.get("APIURL");
    const returnValue = [gettingURL.APIURL, gettingUsername.username, gettingKey.APIKey];
    if (returnValue.includes(undefined)) {
        throw new NoConfigurationError();
    } else {
        return returnValue;
    }
}


class NoConfigurationError extends Error {
    constructor(message?: string) {
        super(message);
        Object.setPrototypeOf(this, new.target.prototype);
        this.name = NoConfigurationError.name
    }
}


// Lookup the bookmark from browser.bookmarks
async function lookupTreeNodeFromBrowser(browserId: string): Promise<browser.bookmarks.BookmarkTreeNode> {
    // FIXME: this can fail, should check to make sure no more than one
    // treeNode
    const treeNodes = await browser.bookmarks.get(browserId)
    const treeNode = treeNodes[0];
    return treeNode
}

async function allTreeNodesFromBrowser(): Promise<Array<browser.bookmarks.BookmarkTreeNode>> {
    // cautiously create a new array rather than reusing because who knows what
    // will happen if we mutate the array returned by getTree
    var unexplored = [(await browser.bookmarks.getTree())[0]];
    var treeNodes = [];
    while (unexplored.length > 0) {
        const treeNode = unexplored.pop();
        // Can't rely on treeNode.type - chrome doesn't populate that field
        if (Object.prototype.hasOwnProperty.call(treeNode, 'url') && treeNode.url !== undefined) {
            treeNodes.push(treeNode);
        }
        if (Object.prototype.hasOwnProperty.call(treeNode, 'children')
            && treeNode.children.length > 0) {
            for (var child of treeNode.children) {
                unexplored.push(child);
            }
        }
    }
    return treeNodes;
}

async function upsertBookmarkIntoBrowser(bookmark: Bookmark): Promise<void> {
    // Unable to read or write tags
    // https://bugzilla.mozilla.org/show_bug.cgi?id=1225916
    const argument = {
        url: bookmark.url.toString(),
        title: bookmark.title,
    }
    if (bookmark.deleted){
        return
    }
    if (bookmark.browserId === null){
        // we're creating
        await browser.bookmarks.create(argument);
    } else {
        // we're updating
        await browser.bookmarks.update(bookmark.browserId, argument);
   }
}

async function allBookmarksFromLocalDb(): Promise<Array<Bookmark>> {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readonly");
        transaction.onerror = function(event){
            console.warn("allBookmarksFromLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.getAll()
        // eslint-disable-next-line no-unused-vars
        request.onsuccess = function(event){
            var rv: Array<Bookmark> = [];
            for (var object of request.result){
                rv.push(Bookmark.from_json(object));
            }
            resolve(rv);
        }
        request.onerror = function(event){
            console.warn("allBookmarksFromLocalDb request failed: %o", event);
            reject();  // could this ever fail?
        }
    });
}

async function lookupBookmarkFromLocalDbByUrl(url: QuarchiveURL): Promise<Bookmark> {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readonly");
        transaction.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByUrl transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.get(url.toString())
        // eslint-disable-next-line no-unused-vars
        request.onsuccess = function(event){
            if (request.result === undefined){
                resolve(null);
            } else {
                const bookmark = Bookmark.from_json(request.result);
                resolve(bookmark);
            }
        }
        request.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByUrl request failed: %o", event);
            reject()
        }
    });
}

// Lookup the bookmark from local db
async function lookupBookmarkFromLocalDbByBrowserId(browserId: string): Promise<Bookmark> {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readonly");
        transaction.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByBrowserId transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var index = objectStore.index("browserId");
        var request = index.get(browserId);
        // eslint-disable-next-line no-unused-vars
        request.onsuccess = function(event){
            if (request.result === undefined) {
                resolve(null);
            } else {
                const bookmark = Bookmark.from_json(request.result);
                resolve(bookmark);
            }
        }
        request.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByBrowserId request failed: %o", event);
            reject();
        }
    });
}

// Insert the bookmark into local db
async function insertBookmarkIntoLocalDb(bookmark: Bookmark): Promise<void> {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readwrite");
        transaction.onerror = function(event){
            console.warn("insertBookmarkIntoLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.add(bookmark.to_db_json())
        // eslint-disable-next-line no-unused-vars
        request.onsuccess = function(event){
            resolve();
        }
        request.onerror = function(event){
            console.warn("insertBookmarkIntoLocalDb request failed: %o, %o", bookmark, event);
            reject();
        }
    });
}

async function updateBookmarkInLocalDb(bookmark: Bookmark): Promise<void> {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readwrite");
        transaction.onerror = function(event){
            console.warn("updateBookmarkInLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.put(bookmark.to_db_json())
        // eslint-disable-next-line no-unused-vars
        request.onsuccess = function(event){
            resolve();
        }
        request.onerror = function(event){
            console.warn("updateBookmarkInLocalDb request failed: %o, %o", bookmark, event);
            reject();
        }
    });
}

async function syncBrowserBookmarksToLocalDb() {
    console.log("starting syncBrowserBookmarksToLocalDb");
    const treeNodes = await allTreeNodesFromBrowser();
    for (var treeNode of treeNodes) {
        let url;
        try {
            url = new QuarchiveURL(treeNode.url);
        } catch (e) {
            if (e instanceof DisallowedSchemeError){
                console.log("skipping %s - disallowed scheme", treeNode.url);
                continue;
            } else {
                throw e;
            }
        }
        const localBookmark = await lookupBookmarkFromLocalDbByUrl(url);
        if (localBookmark === null) {
            const bookmark = new Bookmark(
                url,
                treeNode.title,
                "",
                new Date(treeNode.dateAdded),
                new Date(treeNode.dateAdded),
                false,
                false,
                treeNode.id,
            )
            await insertBookmarkIntoLocalDb(bookmark);
        } else {
            let dbOutOfDate = false;
            if (localBookmark.browserId !== treeNode.id){
                localBookmark.browserId = treeNode.id;
                dbOutOfDate = true;
            }
            if (localBookmark.title !== treeNode.title){
                localBookmark.title = treeNode.title;
                dbOutOfDate = true;
            }
            if (dbOutOfDate){
                console.log("%s out of date in local db, updating", localBookmark.url);
                await updateBookmarkInLocalDb(localBookmark);
            }
        }
    }
    console.log("completed syncBrowserBookmarksToLocalDb");
}

// Syncs a bookmark with the API
async function callSyncAPI(bookmark: Bookmark): Promise<Array<Bookmark>> {
    const sync_body = JSON.stringify(bookmark.to_json());
    console.log("syncing %o", sync_body);
    let [APIURL, username, APIKey] = [undefined, undefined, undefined];
    try {
        [APIURL, username, APIKey] = await getHTTPConfig();
    } catch (e) {
        if (e instanceof NoConfigurationError) {
            console.warn("no configuration - unable to do sync")
            return [];
        } else {
            throw e;
        }
    }
    // FIXME: failure should be logged
    const url = new URL("/sync", APIURL).toString();
    const extensionVersion = browser.runtime.getManifest().version;
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-ndjson",
            "Quarchive-Extension-Version": extensionVersion,
            "Quarchive-Username": username,
            "Quarchive-API-Key": APIKey,
            // FIXME: the below headers are depreciated
            "X-QM-API-Username": username,
            "X-QM-API-Key": APIKey,
        },
        body: sync_body,
    });

    const jsonlines = await response.text()
    console.log("got: '%s'", jsonlines);
    var returnValue = [];
    for (var jsonBookmark of jsonlines.split("\n")){
        // Handle trailing newline
        if (jsonBookmark.length > 0){
            const jsonData = JSON.parse(jsonBookmark);
            const bookmark = Bookmark.from_json(jsonData);
            returnValue.push(bookmark);
        }
    }
    return returnValue;
}

async function callFullSyncAPI(bookmarks: Array<Bookmark>): Promise<Array<Bookmark>>{
    var body = [];
    for (var bookmark of bookmarks) {
        body.push(JSON.stringify(bookmark.to_json()));
    }

    console.log("calling /sync?full=true");
    let [APIURL, username, APIKey] = [undefined, undefined, undefined];
    try {
        [APIURL, username, APIKey] = await getHTTPConfig();
    } catch (e) {
        if (e instanceof NoConfigurationError) {
            console.warn("no configuration - unable to do full sync")
            return [];
        } else {
            throw e;
        }
    }
    const url = new URL("/sync?full=true", APIURL).toString();

    const extensionVersion = browser.runtime.getManifest().version;
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-ndjson",
            "Quarchive-Extension-Version": extensionVersion,
            "Quarchive-Username": username,
            "Quarchive-API-Key": APIKey,
            // FIXME: the below headers are depreciated
            "X-QM-API-Username": username,
            "X-QM-API-Key": APIKey,
        },
        body: body.join("\n"),
    });
    const jsonlines = await response.text()
    var returnValue = [];
    for (var jsonBookmark of jsonlines.split("\n")){
        // Handle trailing newline
        if (jsonBookmark.length > 0){
            const jsonData = JSON.parse(jsonBookmark);
            const bookmark = Bookmark.from_json(jsonData);
            returnValue.push(bookmark);
        }
    }
    return returnValue;
}

export async function fullSync() {
    console.log("starting full sync");
    disableListeners();
    await syncBrowserBookmarksToLocalDb();
    const bookmarksFromServer = await callFullSyncAPI(await allBookmarksFromLocalDb());
    for (var serverBookmark of bookmarksFromServer) {
        const localBookmark = await lookupBookmarkFromLocalDbByUrl(serverBookmark.url);
        if (localBookmark === null) {
            await insertBookmarkIntoLocalDb(serverBookmark);
            await upsertBookmarkIntoBrowser(serverBookmark);
        } else {
            const mergedBookmark = localBookmark.merge(serverBookmark);
            mergedBookmark.browserId = localBookmark.browserId;
            if (!mergedBookmark.equals(localBookmark)) {
                await updateBookmarkInLocalDb(mergedBookmark);
                await upsertBookmarkIntoBrowser(mergedBookmark);
            }
        }
    }
    console.log("ended full sync");
    enableListeners()
}

export function enablePeriodicFullSync(){
    browser.alarms.create("periodicFullSync", {"periodInMinutes": PERIODIC_FULL_SYNC_INTERVAL_IN_MINUTES});
    browser.alarms.onAlarm.addListener(function(alarm) {
        console.log("alarm: %o", alarm);
        fullSync().then();
    });
}

export async function createdListener(
    browserId: string, buggyTreeNode: browser.bookmarks.BookmarkTreeNode) {
    // don't use the second argument, dateAdded is wrong in Firefox - see
    // https://github.com/calpaterson/quarchive/issues/6
    console.log("created: browserId: %s - %o", browserId, buggyTreeNode);
    const treeNode = await lookupTreeNodeFromBrowser(browserId);
    let url;
    try {
        url = new QuarchiveURL(treeNode.url)
    } catch (e) {
        if (e instanceof DisallowedSchemeError){
            console.log("skipping %s - disallowed scheme", treeNode.url);
            return;
        } else {
            throw e;
        }
    }
    let bookmark = new Bookmark(
        url,
        treeNode.title,
        "",
        new Date(treeNode.dateAdded),
        new Date(treeNode.dateAdded),
        false,
        false,
        treeNode.id,
    )
    const bookmarkFromLocalDbIfPresent = await lookupBookmarkFromLocalDbByUrl(url)
    if (bookmarkFromLocalDbIfPresent !== null){
        // Bookmark already exists in db (probably deleted then re-created)
        bookmark = bookmark.merge(bookmarkFromLocalDbIfPresent);
        await updateBookmarkInLocalDb(bookmark);
    } else {
        await insertBookmarkIntoLocalDb(bookmark);
    }
    const bookmarksMergedWithServer = await callSyncAPI(bookmark);
    if (bookmarksMergedWithServer.length > 1) {
        const bookmarkMergedWithServer = bookmarksMergedWithServer[0];
        updateBookmarkInLocalDb(bookmarkMergedWithServer);
        upsertBookmarkIntoBrowser(bookmarkMergedWithServer);
    }
}

async function changeListener(browserId: string, changeInfo) {
    console.log("changed: browserId: %s - %o", browserId, changeInfo);
    const treeNode = await lookupTreeNodeFromBrowser(browserId);
    const bookmarkInDb = await lookupBookmarkFromLocalDbByBrowserId(browserId);
    bookmarkInDb.title = treeNode.title;
    bookmarkInDb.updated = new Date();
    await updateBookmarkInLocalDb(bookmarkInDb);
    const bookmarksMergedWithServer = await callSyncAPI(bookmarkInDb);
    if (bookmarksMergedWithServer.length > 1) {
        const bookmarkMergedWithServer = bookmarksMergedWithServer[0];
        updateBookmarkInLocalDb(bookmarkMergedWithServer);
        upsertBookmarkIntoBrowser(bookmarkMergedWithServer);
    }
}

async function removedListener(browserId: string, removeInfo) {
    console.log("removed browserId: %s - %o", browserId, removeInfo);
    const bookmarkFromBrowser = await lookupBookmarkFromLocalDbByBrowserId(browserId)
    bookmarkFromBrowser.deleted = true;
    bookmarkFromBrowser.browserId = null;
    bookmarkFromBrowser.updated = new Date();
    await updateBookmarkInLocalDb(bookmarkFromBrowser);
    const bookmarksMergedWithServer = await callSyncAPI(bookmarkFromBrowser);
    if (bookmarksMergedWithServer.length > 1) {
        const bookmarkMergedWithServer = bookmarksMergedWithServer[0];
        updateBookmarkInLocalDb(bookmarkMergedWithServer);
        upsertBookmarkIntoBrowser(bookmarkMergedWithServer);
    }
}

async function movedListener(browserId: string, moveInfo) {
    console.log("moved: browserId: %s - %o", browserId, moveInfo);
    // Nothing to do
}

function enableListeners() {
    if (!listenersEnabled){
        browser.bookmarks.onChanged.addListener(changeListener);
        browser.bookmarks.onCreated.addListener(createdListener);
        browser.bookmarks.onMoved.addListener(movedListener);
        browser.bookmarks.onRemoved.addListener(removedListener);
        listenersEnabled = true;
        console.log("listeners enabled");
    }
}

function disableListeners() {
    if (listenersEnabled){
        browser.bookmarks.onChanged.removeListener(changeListener);
        browser.bookmarks.onCreated.removeListener(createdListener);
        browser.bookmarks.onMoved.removeListener(movedListener);
        browser.bookmarks.onRemoved.removeListener(removedListener);
        listenersEnabled = false;
        console.log("listeners disabled");
    }
}

function clearVersion2IDBSchema (db: IDBDatabase): void {
    console.log("clearing idb schema from version 2");
    try {
        db.deleteObjectStore("bookmarks");
    } catch (e) {
        if (e.name === "NotFoundError"){
            // It wasn't there - fine
            console.log("no previous object store existed");
        } else {
            // Something else went wrong - can't continue
            console.error("got exception when trying to delete previous object store")
            throw e;
        }
    }
}

function createIDBSchema(db: IDBDatabase) : void {
    console.log("creating idb schema for version %d", SCHEMA_VERSION);
    var objectStore = db.createObjectStore("bookmarks", {keyPath: "idbKey"});
    objectStore.createIndex("browserId", "browserId", {unique: true});
    objectStore.transaction.oncomplete = function(event){
        console.log("upgrade transaction complete: %o", event);
    }
}

// De facto Main method
if (typeof window !== 'undefined') {
    console.log("starting quarchive load");
    const dbOpenRequest = window.indexedDB.open("quarchive", SCHEMA_VERSION);
    dbOpenRequest.onerror = function(event){
        console.warn("unable to open database: %o", event);
    }
    dbOpenRequest.onupgradeneeded = function (event) {
        console.log("upgrade needed: %o", event);
        let target = <IDBOpenDBRequest> event.target;
        var db = target.result;
        const oldVersion = event.oldVersion;

        console.log("running upgrade %d -> %d", oldVersion, db.version);
        if (oldVersion < 3) {
            clearVersion2IDBSchema(db);
        }
        createIDBSchema(db);

    }
    dbOpenRequest.onsuccess = function(event){
        console.log("opened database: %o, %o", event, dbOpenRequest.result);
        db = dbOpenRequest.result;
        db.onerror = function(event) {
            console.error("db error %o", event);
        }
        fullSync().then(function() {
            enableListeners();
            fullSync().then();  // do one immediately
            enablePeriodicFullSync();
        });
    };

    console.log("quarchive loaded");
};
