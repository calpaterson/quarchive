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

// Lookup the bookmark from local db
function lookupBookmarkFromLocalDb(browserId) {
    throw new Error("not implemented");
}

// Insert the bookmark into local db
function insertBookmarkToLocalDb(bookmark){
    // FIXME: convert this into a promise
    var transaction = db.transaction(["bookmarks"], "readwrite");
    transaction.oncomplete = function(event){
        console.log("insertBookmarkToLocalDb transaction complete: %o", event);
    }
    transaction.onerror = function(event){
        console.warn("insertBookmarkToLocalDb transaction failed: %o", event);
    }
    var objectStore = transaction.objectStore("bookmarks");
    var request = objectStore.add(bookmark)
    request.onsuccess = function(event){
        console.log("insertBookmarkToLocalDb request complete: %o", event);
    }
    request.onerror = function(event){
        console.warn("insertBookmarkToLocalDb request failed: %o, %o", bookmark, event);
    }
}

function updateBookmarkInLocalDb(bookmark){
    throw new Error("not implemented");
}

// Syncs a bookmark with the API
async function syncBookmark(bookmark) {
    const sync_body = {
        "bookmarks": [{
            "url": bookmark.url,
            "timestamp": bookmark.timestamp,
            "title": bookmark.title,
            "unread": bookmark.unread,
            "deleted": bookmark.deleted,
        }]};
    console.log("syncing %o", sync_body);
    // FIXME: failure should be logged
    const response = await fetch(BASE_URL + "/sync", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(sync_body),
    });
    const json = await response.json();
    console.log("got %o", json);
}

async function createdListener(browserId, treeNode) {
    console.log("created: browserId: %s - %o", browserId, treeNode);
    const bookmark = await lookupBookmarkFromBrowser(browserId);
    insertBookmarkToLocalDb(bookmark);
    await syncBookmark(bookmark);
}

async function changeListener(browserId, changeInfo) {
    console.log("changed: browserId: %s - %o", browserId, changeInfo);
    const bookmark = lookupBookmarkFromLocalDb(browserId);
    bookmark.timestamp = Date.now();
    updateBookmarkInLocalDb(bookmark);
    await syncBookmark(bookmark);
}


async function removedListener(browserId, removeInfo) {
    console.log("removed browserId: %s - %o", browserId, removeInfo);
    const bookmark = lookupBookmarkFromLocalDb(browserId)
    bookmark.deleted = true;
    updateBookmarkInLocalDb(bookmark);
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
