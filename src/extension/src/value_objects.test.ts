import { QuarchiveURL } from "./value_objects";

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
