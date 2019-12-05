"use strict";

const BASE_URL = "http://localhost:5000"

const SCHEMA_VERSION = 2;

var db;

class Bookmark {
    constructor(url, title, timestamp, deleted, unread){
        this.url = url;
        this.title = title;
        this.timestamp = timestamp;
        this.deleted = deleted;
        this.unread = unread;
        // this.tags = tags;
    }
}

async function lookupBookmark(id) {
    // FIXME: this can fail, should check to make sure more than one treeNode
    const treeNodes = await browser.bookmarks.get(id)
    const treeNode = treeNodes[0];
    const bookmark = new Bookmark(
        treeNode.url,
        treeNode.title,
        treeNode.dateAdded,
        false,
        false
    );
    console.log("built %o", bookmark);
    return bookmark;
}

function insertBookmark(bookmark){
    var transaction = db.transaction(["bookmarks"], "readwrite");
    transaction.oncomplete = function(event){
        console.log("insertBookmark transaction complete: %o", event);
    }
    transaction.onerror = function(event){
        console.warn("insertBookmark transaction failed: %o", event);
    }
    var objectStore = transaction.objectStore("bookmarks");
    var request = objectStore.add(bookmark)
    request.onsuccess = function(event){
        console.log("insertBookmark request complete: %o", event);
    }
    request.onerror = function(event){
        console.warn("insertBookmark request failed: %o, %o", bookmark, event);
    }
    transaction.commit()
    console.log("commited %o", transaction);
    // FIXME: handle failure
}

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

async function changeListener(id, changeInfo) {
    console.log("changed: id: %s - %o", id, changeInfo);
    const bookmark = await lookupBookmark(id);
    bookmark.timestamp = Date.now();
    // FIXME: need to record this timestamp
    await syncBookmark(bookmark);
}

async function createdListener(id, treeNode) {
    console.log("created: id: %s - %o", id, treeNode);
    const bookmark = await lookupBookmark(id);
    insertBookmark(bookmark);
    await syncBookmark(bookmark);
}

async function movedListener(id, moveInfo) {
    console.log("moved: id: %s - %o", id, moveInfo);
    const bookmark = await lookupBookmark(id);
    await syncBookmark(bookmark);
}

async function removedListener(id, removeInfo) {
    console.log("removed id: %s - %o", id, removeInfo);
    // Can't look up deleted bookmark
    // const bookmark = await lookupBookmark(id);
    // await syncBookmark(bookmark);
}

const dbOpenRequest = window.indexedDB.open("quartermarker", SCHEMA_VERSION);
dbOpenRequest.onerror = function(event){
    console.warn("unable to open database: %o", event);
}
dbOpenRequest.onupgradeneeded = function (event) {
    console.log("upgrade needed: %o", event);
    var db = event.target.result;
    var objectStore = db.createObjectStore("bookmarks", {keyPath: "url"});
    // objectStore.createIndex("browser_id", "id", {unique: true});
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
