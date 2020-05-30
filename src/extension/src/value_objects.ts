export class QuarchiveURL {
    scheme: string;
    netloc: string;
    path: string;
    query: string;
    fragment: string;

    constructor (url_string: string) {
        const js_url = new URL(url_string);
        this.scheme = js_url.protocol.slice(0, -1);
        if (js_url.username !== "" && js_url.password !== "") {
            this.netloc = [js_url.username, ":", js_url.password, "@", js_url.host].join("");
        } else if (js_url.username !== "") {
            this.netloc = [js_url.username, "@", js_url.host].join("");
        } else {
            this.netloc = js_url.host;
        }
        this.path = js_url.pathname;
        this.query = js_url.search.substr(1);
        this.fragment = js_url.hash.substr(1);
    }

    toString(): string {
        let stringArray = [this.scheme, "://", this.netloc, this.path]
        if (this.query !== "") {
            stringArray.push("?");
            stringArray.push(this.query);
        }
        if (this.fragment !== "") {
            stringArray.push("#");
            stringArray.push(this.fragment);
        }
        return stringArray.join("");
    }
}
