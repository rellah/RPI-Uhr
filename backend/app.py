from flask import Flask, jsonify, send_from_directory
import json
import os
import datetime
from ntp_client import get_ntp_time

app = Flask(__name__, static_folder='../frontend', static_url_path='/')

# Set production configuration
app.config.update(
    ENV='production' if os.getenv('FLASK_ENV') == 'production' else 'development',
    DEBUG=os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
)

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
    return jsonify({
        "status": "ok",
        "version": "1.0",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "environment": app.config['ENV']
    })

@app.route('/api/ntp-time')
def ntp_time():
    ntp_time = get_ntp_time()
    if ntp_time:
        return jsonify({"ntp_time": ntp_time})
    return jsonify({"error": "NTP request failed"}), 500

# Only run directly in development mode
if __name__ == '__main__':
    if app.config['ENV'] == 'development':
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        print("This application should be run with a production WSGI server like Gunicorn")