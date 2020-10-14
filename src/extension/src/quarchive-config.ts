import {randomUUID} from "./quarchive-uuid.js"

// export class Config {
//     apiKey: string;
//     username: string;
//     apiURL: string;

//     constructor(apiKey: string, username: string, apiURL: string){
//         this.apiKey = apiKey;
//         this.username = username;
//         this.apiURL = apiURL;
//     }
// }

// export async function getConfig(): Promise<Config> {
//     let fromStorage = await browser.storage.sync.get(["APIKey", "username", "APIURL"]);

//     if (fromStorage.APIURL

//     let apiKey = await browser.storage.sync.get("APIKey") as Optional<string>;
//     let username = await browser.storage.sync.get("username") as Optional<string>;
//     let apiURL = await browser.storage.sync.get("APIURL") as Optional<string>;

//     return new Config(apiKey, username, apiURL)
// }

export async function getClientID(): Promise<string> {
    let wrappedClientID = await browser.storage.sync.get("clientID");
    let clientID;
    if (wrappedClientID["clientID"] !== undefined){
        clientID = wrappedClientID.clientID;
        console.log("found the clientID: %s", clientID);
        return clientID;
    } else {
        clientID = randomUUID();
        await browser.storage.sync.set({"clientID": clientID});
        console.log("minted the clientID: %s", clientID);
        return clientID;
    }
}
