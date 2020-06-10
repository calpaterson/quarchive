import { QuarchiveURL, Bookmark } from "./value_objects";

describe("url class", function(){
    test("url with username and password", function(){
        const urlString = "http://username:password@hostname:1234/sample/path?q=1&a=2#fraggy";
        const quURL = new QuarchiveURL(urlString);

        expect(quURL.toString()).toEqual(urlString);
    });

    test("url with username", function() {
        const urlString = "http://username@hostname:1234/sample/path?q=1&a=2#fraggy";
        const quURL = new QuarchiveURL(urlString);

        expect(quURL.toString()).toEqual(urlString);
    });

    test("normal url", function() {
        const urlString = "http://username@hostname:1234/sample/path";
        const quURL = new QuarchiveURL(urlString);

        expect(quURL.toString()).toEqual(urlString);
    });

    test("url with trailing hash", function(){
        const urlString = "http://hostname:1234/something#";
        const expected = "http://hostname:1234/something";
        const quURL = new QuarchiveURL(urlString);

        expect(quURL.toString()).toEqual(expected);
    });

    test("url with trailing question mark", function(){
        const urlString = "http://hostname:1234/something?";
        const expected = "http://hostname:1234/something";
        const quURL = new QuarchiveURL(urlString);

        expect(quURL.toString()).toEqual(expected);
    });
});

describe("bookmark class", function() {
    const mifid2_start_date = new Date(2018, 0, 3);
    const mifid_plus_one = new Date(2018, 0, 4);

    test("equality", function(){
        let bm1 = new Bookmark(
            new QuarchiveURL("http://example.com"),
            "Example",
            "",
            mifid2_start_date,
            mifid_plus_one,
            false,
            false,
            null
        );
        let bm2 = new Bookmark(
            new QuarchiveURL("http://example.com"),
            "Example",
            "",
            mifid2_start_date,
            mifid_plus_one,
            false,
            false,
            null
        );
        expect(bm1.equals(bm2)).toBe(true);
    });

    test("different dates", function(){
        let bm1 = new Bookmark(
            new QuarchiveURL("http://example.com"),
            "Example",
            "",
            mifid2_start_date,
            mifid2_start_date,
            false,
            false,
            null
        );
        let bm2 = new Bookmark(
            new QuarchiveURL("http://example.com"),
            "Example",
            "",
            mifid2_start_date,
            mifid_plus_one,
            false,
            false,
            null
        );
        expect(bm1.equals(bm2)).toBe(false);
    });

    test("to json", function() {
        let bm1 = new Bookmark(
            new QuarchiveURL("http://example.com"),
            "Example",
            "",
            mifid2_start_date,
            mifid2_start_date,
            false,
            false,
            null
        );
        let expected = {
            "created": mifid2_start_date.toISOString(),
            "deleted": false,
            "description": "",
            "title": "Example",
            "unread": false,
            "updated": mifid2_start_date.toISOString(),
            "url": "http://example.com",
        }
        expect(bm1.to_json()).toEqual(expected);
    })

    test("from json", function() {
        let json = {
            "url": "http://example.com",
            "title": "Example",
            "description": "An example",
            "created": "2020-05-17T16:29:41.161000+00:00",
            "updated": "2020-05-17T16:34:56.709124+00:00",
            "unread": false,
            "deleted": true,
            // TODO:
            // "tag_triples": [["test_tag", "2020-05-18T15:15:15.371887+00:00", false]]
        }

        let bm = Bookmark.from_json(json);

        expect(bm.url).toEqual("http://example.com");
        expect(bm.title).toEqual("Example");
        expect(bm.description).toEqual("An example");
        expect(bm.created).toEqual(new Date(Date.UTC(2020, 4, 17, 16, 29, 41, 161)));
        expect(bm.updated).toEqual(new Date(Date.UTC(2020, 4, 17, 16, 34, 56, 709)));
        expect(bm.unread).toEqual(false);
        expect(bm.deleted).toEqual(true);
    })
});
