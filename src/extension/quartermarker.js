const BASE_URL = "http://localhost:5000"

class Bookmark {
    constructor(url){
        this.url = url;
        this.title = title;
        this.timestamp = timestamp;
        // this.tags = tags;
        // this.deleted = deleted;
        // this.unread = unread;
    }
}

async function lookupBookmark(id) {
    const treeNodes = await browser.bookmarks.get(id)
    const treeNode = treeNodes[0];
    const bookmark = new Bookmark(url=treeNode.url, title=treeNode.title, timestamp=treeNode.dateAdded);
    console.log("built %o", bookmark);
    return bookmark;
}

async function syncBookmark(bookmark) {
    const sync_body = {
        "bookmarks": [{
            "url": bookmark.url,
            "timestamp": bookmark.timestamp,
            "title": bookmark.title,
        }]};
    console.log("syncing %o", sync_body);
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

browser.bookmarks.onChanged.addListener(changeListener);
browser.bookmarks.onCreated.addListener(createdListener);
browser.bookmarks.onMoved.addListener(movedListener);
browser.bookmarks.onRemoved.addListener(removedListener);

console.log("quartermarker loaded");
