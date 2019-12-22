"use strict";

const BASE_URL = "http://localhost:5000"

const SCHEMA_VERSION = 2;

// An hour
const PERIODIC_FULL_SYNC_INTERVAL = 60 * 60 * 1000;

var db;

let listenersEnabled = false;

// This variable is for debugging purposes only
// eslint-disable-next-line no-unused-vars
var periodicFullSyncIntervalId;

class Bookmark {
    constructor(url, title, timestamp, deleted, unread, browserId){
        this.url = url;
        this.title = title;
        this.timestamp = timestamp;
        this.deleted = deleted;
        this.unread = unread;
        this.browserId = browserId;
        // this.tags = tags;
    }

    merge(other) {
        if (this.updated != other.updated) {
            if (this.updated > other.updated) {
                return this
            } else {
                return other
            }
        } else {
            if (this.title.length > other.title.length) {
                return this
            } else {
                return other
            }
        }
    }

    equals(other) {
        // this is utterly absurd but seems to be the way people do things in
        // js
        return JSON.stringify(this) == JSON.stringify(other);
    }

    to_json() {
        return {
            "url": this.url,
            "timestamp": this.timestamp,
            "title": this.title,
            "unread": this.unread,
            "deleted": this.deleted,
        }
    }

    static from_json(json) {
        let browserId;
        if (Object.prototype.hasOwnProperty.call(json, 'browserId')){
            browserId = json.browserId;
        } else {
            browserId = null;
        }
        return new this(
            json.url,
            json.title,
            json.timestamp,
            json.deleted,
            json.unread,
            browserId,
        )
    }

    static fromTreeNode(treeNode) {
        // NOTE: as the bookmarks API does not provide unread or deleted
        // information, those are both assumed to be false
        return new this(
            treeNode.url,
            treeNode.title,
            treeNode.dateAdded,
            false,
            false,
            treeNode.id,
        )
    }
}

async function getCredentials() {
    var gettingKey = await browser.storage.sync.get("APIKey");
    var gettingUsername = await browser.storage.sync.get("username");
    return [gettingUsername.username, gettingKey.APIKey];
}

// Lookup the bookmark from browser.bookmarks
async function lookupBookmarkFromBrowser(browserId) {
    // FIXME: this can fail, should check to make sure no more than one
    // treeNode
    const treeNodes = await browser.bookmarks.get(browserId)
    const treeNode = treeNodes[0];
    const bookmark = Bookmark.fromTreeNode(treeNode);
    return bookmark;
}

async function allBookmarksFromBrowser() {
    // cautiously create a new array rather than reusing because who knows what
    // will happen if we mutate the array returned by getTree
    var unexplored = [(await browser.bookmarks.getTree())[0]];
    var bookmarks = [];
    while (unexplored.length > 0) {
        const treeNode = unexplored.pop();
        if (treeNode.type === 'bookmark') {
            bookmarks.push(Bookmark.fromTreeNode(treeNode));
        }
        if (Object.prototype.hasOwnProperty.call(treeNode, 'children')
            && treeNode.children.length > 0) {
            for (var child of treeNode.children) {
                unexplored.push(child);
            }
        }
    }
    return bookmarks;
}

async function upsertBookmarkIntoBrowser(bookmark) {
    // Unable to read or write tags
    // https://bugzilla.mozilla.org/show_bug.cgi?id=1225916
    const argument = {
        url: bookmark.url,
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

async function allBookmarksFromLocalDb() {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readonly");
        transaction.onerror = function(event){
            console.warn("allBookmarksFromLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.getAll()
        request.onsuccess = function(event){
            var rv = [];
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

async function lookupBookmarkFromLocalDbByUrl(url) {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readonly");
        transaction.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByUrl transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.get(url)
        request.onsuccess = function(event){
            if (request.result === undefined){
                resolve(null);
            } else {
                resolve(Bookmark.from_json(request.result));
            }
        }
        request.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByUrl request failed: %o", event);
            reject()
        }
    });
}

// Lookup the bookmark from local db
async function lookupBookmarkFromLocalDbByBrowserId(browserId) {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readonly");
        transaction.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByBrowserId transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var index = objectStore.index("browserId");
        var request = index.get(browserId);
        request.onsuccess = function(event){
            if (request.result === undefined) {
                resolve(null);
            } else {
                resolve(Bookmark.from_json(request.result));
            }
        }
        request.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByBrowserId request failed: %o", event);
            reject();
        }
    });
}

// Insert the bookmark into local db
async function insertBookmarkIntoLocalDb(bookmark){
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readwrite");
        transaction.onerror = function(event){
            console.warn("insertBookmarkIntoLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.add(bookmark)
        request.onsuccess = function(event){
            resolve();
        }
        request.onerror = function(event){
            console.warn("insertBookmarkIntoLocalDb request failed: %o, %o", bookmark, event);
            reject();
        }
    });
}

async function updateBookmarkInLocalDb(bookmark){
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readwrite");
        transaction.onerror = function(event){
            console.warn("updateBookmarkInLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.put(bookmark)
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
    const browserBookmarks = await allBookmarksFromBrowser();
    for (var browserBookmark of browserBookmarks) {
        const localBookmark = await lookupBookmarkFromLocalDbByUrl(browserBookmark.url);
        if (localBookmark === null) {
            await insertBookmarkIntoLocalDb(browserBookmark);
        } else {
            // FIXME: Can't just merge here, that will blat updated, unread and deleted
            let dbOutOfDate = false;
            if (localBookmark.browserId !== browserBookmark.browserId){
                localBookmark.browserId = browserBookmark.browserId;
                dbOutOfDate = true;
            }
            if (localBookmark.title !== browserBookmark.title){
                localBookmark.title = browserBookmark.title;
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
async function callSyncAPI(bookmark) {
    const sync_body = {
        "bookmarks": [bookmark.to_json()]};
    console.log("syncing %o", sync_body);
    const [username, APIKey] = await getCredentials();
    // FIXME: failure should be logged
    const response = await fetch(BASE_URL + "/sync", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-QM-API-Username": username,
            "X-QM-API-Key": APIKey,
        },
        body: JSON.stringify(sync_body),
    });
    const json = await response.json();
    console.log("got %o", json);
    var returnValue = [];
    for (var responseBookmark of json["bookmarks"]){
        returnValue.push(Bookmark.from_json(responseBookmark));
    }
    return returnValue;
}

async function callFullSyncAPI(bookmarks){
    var body = [];
    for (var bookmark of bookmarks) {
        body.push(bookmark.to_json())
    }
    console.log("calling /sync?full=true");
    const [username, APIKey] = await getCredentials();
    const response = await fetch(BASE_URL + "/sync?full=true", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-QM-API-Username": username,
            "X-QM-API-Key": APIKey,
        },
        body: JSON.stringify({"bookmarks": body}),
    });
    const json = await response.json();
    var returnValue = [];
    for (var responseBookmark of json["bookmarks"]){
        returnValue.push(Bookmark.from_json(responseBookmark));
    }
    return returnValue;
}

async function fullSync() {
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
            serverBookmark.browserId = localBookmark.browserId;
            const mergedBookmark = localBookmark.merge(serverBookmark);
            await updateBookmarkInLocalDb(mergedBookmark);
            await upsertBookmarkIntoBrowser(mergedBookmark);
        }
    }
    console.log("ended full sync");
    enableListeners()
}

function enablePeriodicFullSync(){
    var fullSyncWrapper = function() {
        fullSync().then();
    }
    periodicFullSyncIntervalId = setInterval(fullSyncWrapper, PERIODIC_FULL_SYNC_INTERVAL);
}

async function createdListener(browserId, treeNode) {
    console.log("created: browserId: %s - %o", browserId, treeNode);
    const bookmarkFromBrowser = await lookupBookmarkFromBrowser(browserId);
    await insertBookmarkIntoLocalDb(bookmarkFromBrowser);
    const bookmarksMergedWithServer = await callSyncAPI(bookmarkFromBrowser);
    if (bookmarksMergedWithServer.length > 1) {
        const bookmarkMergedWithServer = bookmarksMergedWithServer[0];
        updateBookmarkInLocalDb(bookmarkMergedWithServer);
        upsertBookmarkIntoBrowser(bookmarkMergedWithServer);
    }
}

async function changeListener(browserId, changeInfo) {
    console.log("changed: browserId: %s - %o", browserId, changeInfo);
    const bookmarkInBrowser = await lookupBookmarkFromBrowser(browserId);
    const bookmarkInDb = await lookupBookmarkFromLocalDbByBrowserId(browserId);
    bookmarkInDb.title = bookmarkInBrowser.title;
    bookmarkInDb.timestamp = Date.now();
    await updateBookmarkInLocalDb(bookmarkInDb);
    const bookmarksMergedWithServer = await callSyncAPI(bookmarkInDb);
    if (bookmarksMergedWithServer.length > 1) {
        const bookmarkMergedWithServer = bookmarksMergedWithServer[0];
        updateBookmarkInLocalDb(bookmarkMergedWithServer);
        upsertBookmarkIntoBrowser(bookmarkMergedWithServer);
    }
}

async function removedListener(browserId, removeInfo) {
    console.log("removed browserId: %s - %o", browserId, removeInfo);
    const bookmarkFromBrowser = await lookupBookmarkFromLocalDbByBrowserId(browserId)
    bookmarkFromBrowser.deleted = true;
    bookmarkFromBrowser.browserId = null;
    await updateBookmarkInLocalDb(bookmarkFromBrowser);
    const bookmarksMergedWithServer = await callSyncAPI(bookmarkFromBrowser);
    if (bookmarksMergedWithServer.length > 1) {
        const bookmarkMergedWithServer = bookmarksMergedWithServer[0];
        updateBookmarkInLocalDb(bookmarkMergedWithServer);
        upsertBookmarkIntoBrowser(bookmarkMergedWithServer);
    }
}

async function movedListener(browserId, moveInfo) {
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

const dbOpenRequest = window.indexedDB.open("quartermarker", SCHEMA_VERSION);
dbOpenRequest.onerror = function(event){
    console.warn("unable to open database: %o", event);
}
dbOpenRequest.onupgradeneeded = function (event) {
    console.log("upgrade needed: %o", event);
    var db = event.target.result;
    var objectStore = db.createObjectStore("bookmarks", {keyPath: "url"});
    objectStore.createIndex("browserId", "browserId", {unique: true});
    objectStore.transaction.oncomplete = function(event) {
        console.log("upgrade transaction complete: %o", event);
    }
}
dbOpenRequest.onsuccess = function(event){
    console.log("opened database: %o, %o", event, dbOpenRequest.result);
    db = dbOpenRequest.result;
    db.onerror = function(event) {
        console.error("db error %o", event);
    }
    fullSync().then(function() {
        enableListeners();
        enablePeriodicFullSync();
    });
};

console.log("quartermarker loaded");
