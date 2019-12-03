const BASE_URL = "http://localhost:5000"

// class Bookmark {
//     constructor(url, title, timestamp, tags, deleted){
//         this.url = url;
//         this.title = title;
//         this.timestamp = timestamp;
//         this.tags = tags;
//         this.deleted = deleted;
//         this.unread = unread;
//     }
// }

async function changeListener(id, changeInfo) {
    console.log("changed: id: %s - %o", id, changeInfo);
    const bookmarks = await browser.bookmarks.get(id)
    const bookmark = bookmarks[0];
    const sync_body = {
        "bookmarks": [{
            "url": bookmark.url,
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

function createdListener(id, bookmark) {
    console.log("created: id: %s - %o", id, bookmark);
}

function movedListener(id, moveInfo) {
    console.log("moved: id: %s - %o", id, moveInfo);
}

function removedListener(id, removeInfo) {
    console.log("removed id: %s - %o", id, removeInfo);
}

browser.bookmarks.onChanged.addListener(changeListener);
browser.bookmarks.onCreated.addListener(createdListener);
browser.bookmarks.onMoved.addListener(movedListener);
browser.bookmarks.onRemoved.addListener(removedListener);

console.log("quartermarker loaded");
