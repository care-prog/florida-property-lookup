from flask import Flask, render_template, request, jsonify
from property_lookup import lookup_property

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    address = request.json.get("address", "").strip()
    if not address:
        return jsonify({"error": "Please enter an address."})
    result = lookup_property(address)
    return jsonify(result)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
