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
    const mifid_start_date = new Date(2018, 0, 3);
    const mifid_plus_one = new Date(2018, 0, 4);

    test("equality", function(){
        let bm1 = new Bookmark(
            "http://example.com",
            "Example",
            "",
            mifid_start_date,
            mifid_plus_one,
            false,
            false,
            null
        );
        let bm2 = new Bookmark(
            "http://example.com",
            "Example",
            "",
            mifid_start_date,
            mifid_plus_one,
            false,
            false,
            null
        );
        expect(bm1.equals(bm2)).toBe(true);
    });

    test("different dates", function(){
        let bm1 = new Bookmark(
            "http://example.com",
            "Example",
            "",
            mifid_start_date,
            mifid_start_date,
            false,
            false,
            null
        );
        let bm2 = new Bookmark(
            "http://example.com",
            "Example",
            "",
            mifid_start_date,
            mifid_plus_one,
            false,
            false,
            null
        );
        expect(bm1.equals(bm2)).toBe(false);
    });
});
