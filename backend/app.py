from flask import Flask, jsonify, send_from_directory
import json
import os

app = Flask(__name__, static_folder='../frontend', static_url_path='/')

# Pfad zur Konfigurationsdatei
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'breaks.json')

@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/config')
def get_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        return jsonify(config)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/health')
def health_check():
    return jsonify({"status": "ok", "version": "1.0"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)