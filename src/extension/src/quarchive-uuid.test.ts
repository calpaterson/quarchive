import { randomUUID } from "./quarchive-uuid"

describe("uuid generator", function(){
    test("right format", function(){
        const u = randomUUID();
        expect(u).toMatch(/[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}/);
    });
})
