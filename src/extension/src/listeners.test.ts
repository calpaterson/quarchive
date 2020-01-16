import { createdListener } from "./quarchive-background"

const chrome = require('sinon-chrome/extensions');

describe("listeners", function() {
    beforeEach(function() {
        (global as any).browser = chrome;
    });

    test("creation event for a new bookmark", async function (){
        // SETUP
        // mock browser.bookmarks
        const createDetails = {
            title: "Example",
            url: "http://example.com",
            type: "bookmark",
        };
        const treeNodeAsInserted = await (global as any).browser.bookmarks.create(
            createDetails
        );
        // mock indexeddb
        // mock fetch

        // test
        // call createdListener
        // createdListener("xyz", {"id": "xyz", "title": "Example.com"});

        // assert
        // assert bookmark in db
        // assert bookmark was sent
    });
});
