const BASE_URL = "http://localhost:5000/"

function changeListener(id, changeInfo) {
    console.log("changed: id: %s - %o", id, changeInfo);
    const response = fetch(BASE_URL + "ok").then(async function (response) {
        const json = await response.json();
        console.log("got %o", json);
    });
};

function createdListener(id, bookmark) {
    console.log("created: id: %s - %o", id, bookmark);
};

function movedListener(id, moveInfo) {
    console.log("moved: id: %s - %o", id, moveInfo);
};

function removedListener(id, removeInfo) {
    console.log("removed id: %s - %o", id, removeInfo);
};

browser.bookmarks.onChanged.addListener(changeListener);
browser.bookmarks.onCreated.addListener(createdListener);
browser.bookmarks.onMoved.addListener(movedListener);
browser.bookmarks.onRemoved.addListener(removedListener);

console.log("quartermarker loaded");
