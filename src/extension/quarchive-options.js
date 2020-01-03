var saveOptions = function(e){
    browser.storage.sync.set({
        APIURL: document.querySelector("#api-url").value,
        username: document.querySelector("#username").value,
        APIKey: document.querySelector("#api-key").value,
    });
    e.preventDefault()
}

var restoreOptions = function(){
    var gettingUsername = browser.storage.sync.get("username");
    gettingUsername.then(function (result) {
        document.querySelector("#username").value = result.username;
    })

    var gettingKey = browser.storage.sync.get("APIKey");
    gettingKey.then(function (result) {
        document.querySelector("#api-key").value = result.APIKey;
    })

    var gettingURL = browser.storage.sync.get("APIURL");
    gettingURL.then(function (result) {
        document.querySelector("#api-url").value = result.APIURL;
    })
}

document.addEventListener('DOMContentLoaded', restoreOptions);
document.querySelector("form").addEventListener("submit", saveOptions);
