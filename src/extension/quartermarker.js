"use strict";

const BASE_URL = "http://localhost:5000"

const SCHEMA_VERSION = 2;

var db;

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

    merge(other){
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
}

async function getCredentials() {
    var gettingKey = await browser.storage.sync.get("APIKey");
    var gettingUsername = await browser.storage.sync.get("username");
    return [gettingUsername.username, gettingKey.APIKey];
}

// Lookup the bookmark from browser.bookmarks
async function lookupBookmarkFromBrowser(browserId) {
    // FIXME: this can fail, should check to make sure more than one treeNode
    const treeNodes = await browser.bookmarks.get(browserId)
    const treeNode = treeNodes[0];
    const bookmark = new Bookmark(
        treeNode.url,
        treeNode.title,
        treeNode.dateAdded,
        false,
        false,
        browserId,
    );
    console.log("built %o", bookmark);
    return bookmark;
}

async function upsertBookmarkIntoBrowser(bookmark) {
    // Unable to read or write tags
    // https://bugzilla.mozilla.org/show_bug.cgi?id=1225916
    const argument = {
        url: bookmark.url,
        title: bookmark.title,
    }
    if (bookmark.browserId === null){
        // we're creating
        await browser.bookmarks.create(argument);
    } else {
        // we're updating
        await browser.bookmarks.update(bookmark.browserId, argument);
    }
}

// Lookup the bookmark from local db
async function lookupBookmarkFromLocalDbByBrowserId(browserId) { // FIXME: ByBrowserId
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readonly");
        transaction.oncomplete = function(event){
            console.log("lookupBookmarkFromLocalDbByBrowserId transaction complete: %o", event);
        }
        transaction.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByBrowserId transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var index = objectStore.index("browserId");
        var request = index.get(browserId);
        request.onsuccess = function(event){
            console.log("lookupBookmarkFromLocalDbByBrowserId request complete: %o", event);
            resolve(request.result);
        }
        request.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByBrowserId request failed: %o", event);
            reject(); // FIXME: what if it doesn't exist?
        }
    });
}

async function allBookmarksFromLocalDb() {
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readonly");
        transaction.oncomplete = function(event){
            console.log("allBookmarksFromLocalDb transaction complete: %o", event);
        }
        transaction.onerror = function(event){
            console.warn("allBookmarksFromLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var index = objectStore.index("browserId");
        var request = index.getAll()
        request.onsuccess = function(event){
            console.log("allBookmarksFromLocalDb request complete: %o", event);
            resolve(request.result);
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
        transaction.oncomplete = function(event){
            console.log("lookupBookmarkFromLocalDbByUrl transaction complete: %o", event);
        }
        transaction.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByUrl transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.get(url)
        request.onsuccess = function(event){
            console.log("lookupBookmarkFromLocalDbByUrl request complete: %o", event);
            resolve(request.result);
        }
        request.onerror = function(event){
            console.warn("lookupBookmarkFromLocalDbByUrl request failed: %o", event);
            reject(); // FIXME: what if it doesn't exist?
        }
    });
}

// Insert the bookmark into local db
async function insertBookmarkIntoLocalDb(bookmark){
    return new Promise(function(resolve, reject) {
        var transaction = db.transaction(["bookmarks"], "readwrite");
        transaction.oncomplete = function(event){
            console.log("insertBookmarkIntoLocalDb transaction complete: %o", event);
        }
        transaction.onerror = function(event){
            console.warn("insertBookmarkIntoLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.add(bookmark)
        request.onsuccess = function(event){
            console.log("insertBookmarkIntoLocalDb request complete: %o", event);
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
        transaction.oncomplete = function(event){
            console.log("updateBookmarkInLocalDb transaction complete: %o", event);
        }
        transaction.onerror = function(event){
            console.warn("updateBookmarkInLocalDb transaction failed: %o", event);
        }
        var objectStore = transaction.objectStore("bookmarks");
        var request = objectStore.put(bookmark)
        request.onsuccess = function(event){
            console.log("updateBookmarkInLocalDb request complete: %o", event);
            resolve();
        }
        request.onerror = function(event){
            console.warn("updateBookmarkInLocalDb request failed: %o, %o", bookmark, event);
            reject();
        }
    });
}

async function copyBrowserBookmarksToLocalDb(){
    // TODO
}

// Syncs a bookmark with the API
async function syncBookmark(bookmark) {
    const sync_body = {
        "bookmarks": [{  // FIXME: refactor this into to_json and from_json
            "url": bookmark.url,
            "timestamp": bookmark.timestamp,
            "title": bookmark.title,
            "unread": bookmark.unread,
            "deleted": bookmark.deleted,
        }]};
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
    // FIXME: if we get back something different we should merge it
}

async function fullSyncBookmarks(bookmarks){
    // TODO
}

async function fullSync() {
    console.log("starting full sync");
    await copyBrowserBookmarksToLocalDb();
    const bookmarksFromLocalDb = await allBookmarksFromLocalDb();
    const bookmarksFromServer = await fullSyncBookmarks(bookmarksFromLocalDb);
    // delete bookmarksFromLocalDb // should consider this, it's probably pretty large
    for (var serverBookmark of bookmarksFromServer) {
        const localBookmark = lookupBookmarkFromLocalDbByUrl(serverBookmark.url);
        serverBookmark.browserId = localBookmark.browserId;
        const mergedBookmark = localBookmark.merge(serverBookmark);
        insertBookmarkIntoLocalDb(mergedBookmark);
        upsertBookmarkIntoBrowser(mergedBookmark);
        console.log("merged %o", mergedBookmark);
    }
    console.log("ended full sync");
}

async function createdListener(browserId, treeNode) {
    console.log("created: browserId: %s - %o", browserId, treeNode);
    const bookmark = await lookupBookmarkFromBrowser(browserId);
    await insertBookmarkIntoLocalDb(bookmark);
    await syncBookmark(bookmark);
}

async function changeListener(browserId, changeInfo) {
    console.log("changed: browserId: %s - %o", browserId, changeInfo);
    const bookmarkInBrowser = await lookupBookmarkFromBrowser(browserId);
    const bookmarkInDb = await lookupBookmarkFromLocalDbByBrowserId(browserId);
    bookmarkInDb.title = bookmarkInBrowser.title;
    bookmarkInDb.timestamp = Date.now();
    await updateBookmarkInLocalDb(bookmarkInDb);
    await syncBookmark(bookmarkInDb);
}

async function removedListener(browserId, removeInfo) {
    console.log("removed browserId: %s - %o", browserId, removeInfo);
    const bookmark = await lookupBookmarkFromLocalDbByBrowserId(browserId)
    bookmark.deleted = true;
    await updateBookmarkInLocalDb(bookmark);
    await syncBookmark(bookmark);
}

async function movedListener(browserId, moveInfo) {
    console.log("moved: browserId: %s - %o", browserId, moveInfo);
    // Nothing to do
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
    browser.bookmarks.onChanged.addListener(changeListener);
    browser.bookmarks.onCreated.addListener(createdListener);
    browser.bookmarks.onMoved.addListener(movedListener);
    browser.bookmarks.onRemoved.addListener(removedListener);
};


console.log("quartermarker loaded");
