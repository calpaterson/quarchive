var saveOptions = function(e){
    browser.storage.sync.set({
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
}

document.addEventListener('DOMContentLoaded', restoreOptions);
document.querySelector("form").addEventListener("submit", saveOptions);
