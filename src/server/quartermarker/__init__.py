import flask
from flask_cors import CORS

app = flask.Flask("quartermarker")
CORS(app)

@app.route("/ok")
def ok():
    return flask.json.jsonify({"ok": True})

def main():
    app.run()
