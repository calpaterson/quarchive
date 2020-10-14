import './crypto.mock'
import './browser.mock'
import {randomUUID} from "./quarchive-uuid"
import {getClientID} from "./quarchive-config"

describe("client id", function(){
    test("getting the client id for the first time", async function(){
        const clientID = await getClientID();
        expect(clientID).toHaveLength(36);
        // @ts-ignore
        expect(browser.storage.sync._contents["clientID"]).toBe(clientID);
    });
    test("getting the client id after that", async function(){
        const clientID = await getClientID();
        expect(await getClientID()).toBe(clientID);
    });
});
