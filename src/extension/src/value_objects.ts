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


export class Bookmark {
    url: string;
    title: string;
    description: string;
    created: Date;
    updated: Date;
    deleted: boolean;
    unread: boolean;
    browserId: string;
    constructor(
        url: string,
        title: string,
        description: string,
        created: Date,
        updated: Date,
        deleted: boolean,
        unread:boolean,
        browserId: string
    ){
        this.url = url;
        this.title = title;
        this.description = description,

        this.created = created;
        this.updated = updated;

        this.deleted = deleted;
        this.unread = unread;

        this.browserId = browserId;
        // this.tags = tags;
    }

    merge(other: Bookmark): Bookmark {
        let moreRecent;
        let minCreated;
        let maxUpdated;
        if (this.updated > other.updated) {
            moreRecent = this;
        } else if (other.updated > this.updated) {
            moreRecent = other;
        } else {
            const thisLengths = this.title.length + this.description.length;
            const otherLengths = other.title.length + other.description.length;
            if (otherLengths > thisLengths) {
                moreRecent = other;
            } else {
                moreRecent = this;
            }
        }
        if (this.created < other.created){
            minCreated = this.created;
        } else {
            minCreated = other.created;
        }
        if (this.updated > other.updated) {
            maxUpdated = this.updated;
        } else {
            maxUpdated = other.updated;
        }
        return new Bookmark(
            this.url,
            moreRecent.title,
            moreRecent.description,
            minCreated,
            maxUpdated,
            moreRecent.deleted,
            moreRecent.unread,
            moreRecent.browserId
        )
    }

    equals(other: Bookmark) {
        const fields = [
            "url",
            "title",
            "description",
            "created",
            "updated",
            "deleted",
            "unread",
            "browserId" // should this be included?
        ];
        for (var field of fields) {
            if (this[field] !== other[field]){
                return false;
            }
        }
        return true;
    }

    to_json() {
        return {
            "created": this.created.toISOString(),
            "deleted": this.deleted,
            "description": this.description,
            "title": this.title,
            "unread": this.unread,
            "updated": this.updated.toISOString(),
            "url": this.url,
        }
    }

    to_db_json() {
        let json = this.to_json();
        json["browserId"] = this.browserId;
        return json
    }

    static from_json(json) {
        let browserId;
        if (Object.prototype.hasOwnProperty.call(json, 'browserId')){
            browserId = json.browserId;
        } else {
            browserId = null;
        }
        return new this(
            json.url,
            json.title,
            json.description,
            new Date(json.created),
            new Date(json.updated),
            json.deleted,
            json.unread,
            browserId,
        )
    }
}
