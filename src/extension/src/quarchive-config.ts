import {randomUUID} from "./quarchive-uuid.js"


export async function getClientID(): Promise<string> {
    let wrappedClientID = await browser.storage.sync.get("clientID");
    let clientID;
    if (wrappedClientID["clientID"] !== undefined){
        clientID = wrappedClientID.clientID;
        console.debug("found the clientID: %s", clientID);
        return clientID;
    } else {
        clientID = randomUUID();
        await browser.storage.sync.set({"clientID": clientID});
        console.log("minted the clientID: %s", clientID);
        return clientID;
    }
}
