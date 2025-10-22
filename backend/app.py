import datetime
import os
from functools import wraps
from typing import Callable, Dict, Tuple

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from ntp_client import get_ntp_time
from storage import (
    BreakNotFoundError,
    BreakStore,
    BreakValidationError,
)

app = Flask(
    __name__,
    static_folder="../frontend",
    static_url_path="/",
    template_folder="templates",
)

# Set production configuration
app.config.update(
    ENV="production" if os.getenv("FLASK_ENV") == "production" else "development",
    DEBUG=os.getenv("FLASK_DEBUG", "false").lower() == "true",
)

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "breaks.db")
DEFAULT_SEED_PATH = os.path.join(BASE_DIR, "breaks.json")
DB_PATH = os.getenv("BREAKS_DB_PATH", DEFAULT_DB_PATH)
SEED_PATH = os.getenv("BREAKS_SEED_PATH", DEFAULT_SEED_PATH)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
AUTH_REALM = os.getenv("ADMIN_REALM", "Break Administration")
API_VERSION = "1.1"

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    ADMIN_USERNAME = ADMIN_USERNAME or "admin"
    ADMIN_PASSWORD = ADMIN_PASSWORD or "admin"
    app.logger.warning(
        "Using default admin credentials. Override ADMIN_USERNAME and ADMIN_PASSWORD."
    )

store = BreakStore(DB_PATH)
store.seed_from_json(SEED_PATH)


def _get_admin_credentials() -> Tuple[str, str]:
    return ADMIN_USERNAME, ADMIN_PASSWORD


def requires_auth(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        expected_user, expected_pass = _get_admin_credentials()
        if (
            not auth
            or auth.username != expected_user
            or auth.password != expected_pass
        ):
            return _auth_challenge()
        return func(*args, **kwargs)

    return wrapper


def _auth_challenge() -> Response:
    return Response(
        status=401,
        headers={"WWW-Authenticate": f'Basic realm="{AUTH_REALM}"'},
    )


def _get_changed_by() -> str:
    auth = request.authorization
    if auth:
        return auth.username or "unknown"
    return "unknown"


def _sanitize_break_payload(entry: Dict) -> Dict:
    return {
        "id": entry.get("id"),
        "start": entry.get("start"),
        "end": entry.get("end"),
        "description": entry.get("description") or "",
    }

@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/admin")
@requires_auth
def admin_view():
    return render_template("admin.html", api_version=API_VERSION)

@app.route('/api/config')
def get_config():
    breaks = [_sanitize_break_payload(item) for item in store.list_breaks()]
    return jsonify({"version": API_VERSION, "breaks": breaks})

@app.route("/api/breaks", methods=["GET"])
def list_breaks():
    breaks = [_sanitize_break_payload(item) for item in store.list_breaks()]
    return jsonify(
        {
            "breaks": breaks,
            "metadata": {"count": len(breaks), "version": API_VERSION},
        }
    )

@app.route("/api/breaks", methods=["POST"])
@requires_auth
def create_break():
    payload = request.get_json(force=True, silent=True) or {}
    start = payload.get("start")
    end = payload.get("end")
    description = payload.get("description", "")
    try:
        created = store.create_break(
            start=start,
            end=end,
            description=description,
            changed_by=_get_changed_by(),
        )
    except BreakValidationError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.exception("Failed to create break")
        return jsonify({"error": str(error)}), 500

    return jsonify(_sanitize_break_payload(created)), 201

@app.route("/api/breaks/<int:break_id>", methods=["PUT"])
@requires_auth
def update_break(break_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    start = payload.get("start")
    end = payload.get("end")
    description = payload.get("description", "")
    try:
        updated = store.update_break(
            break_id=break_id,
            start=start,
            end=end,
            description=description,
            changed_by=_get_changed_by(),
        )
    except BreakValidationError as error:
        return jsonify({"error": str(error)}), 400
    except BreakNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        app.logger.exception("Failed to update break %s", break_id)
        return jsonify({"error": str(error)}), 500

    return jsonify(_sanitize_break_payload(updated))

@app.route("/api/breaks/<int:break_id>", methods=["DELETE"])
@requires_auth
def delete_break(break_id: int):
    try:
        store.delete_break(break_id=break_id, changed_by=_get_changed_by())
    except BreakNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        app.logger.exception("Failed to delete break %s", break_id)
        return jsonify({"error": str(error)}), 500

    return jsonify({"status": "deleted", "id": break_id})

@app.route("/api/breaks/<int:break_id>/revisions", methods=["GET"])
@requires_auth
def list_break_revisions(break_id: int):
    revisions = store.list_revisions(break_id=break_id)
    return jsonify({"revisions": revisions})

@app.route("/api/revisions/<int:revision_id>/restore", methods=["POST"])
@requires_auth
def restore_break_revision(revision_id: int):
    try:
        restored = store.restore_revision(
            revision_id=revision_id, changed_by=_get_changed_by()
        )
    except BreakValidationError as error:
        return jsonify({"error": str(error)}), 400
    except BreakNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        app.logger.exception("Failed to restore revision %s", revision_id)
        return jsonify({"error": str(error)}), 500

    return jsonify(_sanitize_break_payload(restored))

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
