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
    constructor(url, title, description, created, updated, deleted, unread, browserId){
        this.url = url;
        this.title = title;
        this.description = description,

        this.created = created;
        this.updated = updated;

        this.deleted = deleted;
        this.unread = unread;

        this.browserId = browserId;
        // this.tags = tags;
    }

    merge(other) {
        let moreRecent;
        let minCreated;
        let maxUpdated;
        if (this.updated > other.updated) {
            moreRecent = this;
        } else if (other.updated > this.updated) {
            moreRecent = other;
        } else {
            const thisLengths = this.title.length + this.description.length;
            const otherLengths = other.title.length + other.description.length;
            if (otherLengths > thisLengths) {
                moreRecent = other;
            } else {
                moreRecent = this;
            }
        }
        if (this.created < other.created){
            minCreated = this.created;
        } else {
            minCreated = other.created;
        }
        if (this.updated > other.updated) {
            maxUpdated = this.updated;
        } else {
            maxUpdated = other.updated;
        }
        return new Bookmark(
            this.url,
            moreRecent.title,
            moreRecent.description,
            minCreated,
            maxUpdated,
            moreRecent.deleted,
            moreRecent.unread,
            moreRecent.browserId
        )
    }

    equals(other) {
        // this is utterly absurd but seems to be the way people do things in
        // js
        return JSON.stringify(this) == JSON.stringify(other);
    }

    to_json() {
        return {
            "created": this.created.toISOString(),
            "deleted": this.deleted,
            "description": this.description,
            "title": this.title,
            "unread": this.unread,
            "updated": this.updated.toISOString(),
            "url": this.url,
        }
    }

    to_db_json() {
        let json = this.to_json();
        json.browserId = this.browserId;
        return json
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
            json.description,
            new Date(json.created),
            new Date(json.updated),
            json.deleted,
            json.unread,
            browserId,
        )
    }
}

async function getCredentials() {
    var gettingKey = await browser.storage.sync.get("APIKey");
    var gettingUsername = await browser.storage.sync.get("username");
    return [gettingUsername.username, gettingKey.APIKey];
}

// Lookup the bookmark from browser.bookmarks
async function lookupTreeNodeFromBrowser(browserId) {
    // FIXME: this can fail, should check to make sure no more than one
    // treeNode
    const treeNodes = await browser.bookmarks.get(browserId)
    const treeNode = treeNodes[0];
    return treeNode
}

async function allTreeNodesFromBrowser() {
    // cautiously create a new array rather than reusing because who knows what
    // will happen if we mutate the array returned by getTree
    var unexplored = [(await browser.bookmarks.getTree())[0]];
    var treeNodes = [];
    while (unexplored.length > 0) {
        const treeNode = unexplored.pop();
        if (treeNode.type === 'bookmark') {
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
        // eslint-disable-next-line no-unused-vars
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
async function lookupBookmarkFromLocalDbByBrowserId(browserId) {
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
async function insertBookmarkIntoLocalDb(bookmark){
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

async function updateBookmarkInLocalDb(bookmark){
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
        const localBookmark = await lookupBookmarkFromLocalDbByUrl(treeNode.url);
        if (localBookmark === null) {
            const bookmark = new Bookmark(
                treeNode.url,
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

function enablePeriodicFullSync(){
    var fullSyncWrapper = function() {
        fullSync().then();
    }
    periodicFullSyncIntervalId = setInterval(fullSyncWrapper, PERIODIC_FULL_SYNC_INTERVAL);
}

async function createdListener(browserId, treeNode) {
    console.log("created: browserId: %s - %o", browserId, treeNode);
    let bookmark = new Bookmark(
        treeNode.url,
        treeNode.title,
        "",
        new Date(treeNode.dateAdded),
        new Date(treeNode.dateAdded),
        false,
        false,
        treeNode.id,
    )
    const bookmarkFromLocalDbIfPresent = await lookupBookmarkFromLocalDbByUrl(treeNode.url)
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

async function changeListener(browserId, changeInfo) {
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

async function removedListener(browserId, removeInfo) {
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

const dbOpenRequest = window.indexedDB.open("quarchive", SCHEMA_VERSION);
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

console.log("quarchive loaded");
