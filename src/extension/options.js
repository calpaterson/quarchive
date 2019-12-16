var saveOptions = function(e){
    browser.storage.sync.set({
        APIKey: document.querySelector("#api-key").value
    });
    e.preventDefault()
}

var restoreOptions = function(){
    var gettingKey = browser.storage.sync.get("APIKey");
    gettingKey.then(function (result) {
        document.querySelector("#api-key").value = result.APIKey;
    })
}

document.addEventListener('DOMContentLoaded', restoreOptions);
document.querySelector("form").addEventListener("submit", saveOptions);
