import { Bookmark } from "./quarchive-background";

test("bookmark equality", function(){
    let bm1 = new Bookmark(
        "http://example.com",
        "Example",
        "",
        new Date(),
        new Date(),
        false,
        false,
        null
    );
    let bm2 = new Bookmark(
        "http://example.com",
        "Example",
        "",
        new Date(),
        new Date(),
        false,
        false,
        null
    );
    expect(bm1.equals(bm2)).toBe(true);
});
