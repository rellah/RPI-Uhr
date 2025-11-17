import datetime
import os
from functools import wraps
from typing import Callable, Dict, Tuple
import werkzeug.utils

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
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
DATA_DIR = os.path.join(STORAGE_DIR, "data")
SOUNDS_DIR = os.path.join(STORAGE_DIR, "sounds")
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

# Ensure storage directories exist
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SOUNDS_DIR, exist_ok=True)

# Handle migration from old directory structure
def migrate_storage():
    """Migrate data and sounds from old directory structure to new storage directory"""
    old_data_dir = os.path.join(BASE_DIR, "data")
    old_sounds_dir = os.path.join(BASE_DIR, "sounds")

    # Migrate database if old directory exists and new one doesn't have data
    if os.path.exists(old_data_dir) and not os.path.exists(os.path.join(DATA_DIR, "breaks.db")):
        old_db = os.path.join(old_data_dir, "breaks.db")
        if os.path.exists(old_db):
            import shutil
            shutil.copy2(old_db, os.path.join(DATA_DIR, "breaks.db"))
            app.logger.info("Migrated database from old directory structure")

    # Migrate sounds if old directory exists and new one is empty
    if os.path.exists(old_sounds_dir) and (not os.path.exists(SOUNDS_DIR) or not os.listdir(SOUNDS_DIR)):
        import shutil
        for filename in os.listdir(old_sounds_dir):
            if filename.lower().endswith(('.mp3', '.wav')):
                old_file = os.path.join(old_sounds_dir, filename)
                new_file = os.path.join(SOUNDS_DIR, filename)
                shutil.copy2(old_file, new_file)
        app.logger.info("Migrated sound files from old directory structure")

# Perform migration
migrate_storage()

# Initialize default sound settings if they don't exist
def initialize_default_sounds():
    default_sounds = [
        {"sound_type": "break_start", "file_path": "", "volume": 50, "enabled": True},
        {"sound_type": "break_end", "file_path": "", "volume": 50, "enabled": True}
    ]

    for sound_config in default_sounds:
        try:
            existing = store.get_sound_setting(sound_config["sound_type"])
            if existing is None:
                store.update_sound_setting(
                    sound_type=sound_config["sound_type"],
                    file_path=sound_config["file_path"],
                    volume=sound_config["volume"],
                    enabled=sound_config["enabled"]
                )
        except Exception as e:
            app.logger.error(f"Failed to initialize sound {sound_config['sound_type']}: {e}")
            # Continue with next sound type

initialize_default_sounds()


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

@app.route("/api/sounds", methods=["GET"])
@requires_auth
def get_sound_settings():
    """Get all sound settings."""
    try:
        sounds = store.get_sound_settings()
        return jsonify({"sounds": sounds})
    except Exception as error:
        app.logger.exception("Failed to get sound settings")
        return jsonify({"error": str(error)}), 500

@app.route("/api/sounds", methods=["POST"])
@requires_auth
def update_sound_settings():
    """Update sound settings."""
    payload = request.get_json(force=True, silent=True) or {}
    sound_type = payload.get("sound_type")
    file_path = payload.get("file_path")
    volume = payload.get("volume")
    enabled = payload.get("enabled")

    if not sound_type or sound_type not in ["break_start", "break_end"]:
        return jsonify({"error": "Invalid sound type"}), 400

    try:
        updated = store.update_sound_setting(
            sound_type=sound_type,
            file_path=file_path,
            volume=volume,
            enabled=enabled
        )
        return jsonify(updated)
    except Exception as error:
        app.logger.exception("Failed to update sound setting")
        return jsonify({"error": str(error)}), 500

@app.route("/api/sounds/upload", methods=["POST"])
@requires_auth
def upload_sound():
    """Upload a sound file."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    sound_type = request.form.get('sound_type')

    if not sound_type or sound_type not in ["break_start", "break_end", "custom"]:
        return jsonify({"error": "Invalid sound type"}), 400

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Check file extension
    allowed_extensions = {'.mp3', '.wav'}
    filename = file.filename.lower()
    file_ext = os.path.splitext(filename)[1]

    if file_ext not in allowed_extensions:
        return jsonify({"error": "Only MP3 and WAV files are allowed"}), 400

    # Check file size (10MB limit)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > 10 * 1024 * 1024:  # 10MB
        return jsonify({"error": "File size must be less than 10MB"}), 400

    try:
        if sound_type == "custom":
            # For library uploads, use the original filename
            safe_filename = werkzeug.utils.secure_filename(file.filename)

            # Handle filename conflicts by appending a number if needed
            base_name, ext = os.path.splitext(safe_filename)
            counter = 1
            final_filename = safe_filename

            while os.path.exists(os.path.join(SOUNDS_DIR, final_filename)):
                final_filename = f"{base_name}_{counter}{ext}"
                counter += 1

            file_path = os.path.join(SOUNDS_DIR, final_filename)

            # Save file
            file.save(file_path)

            # Return library file info
            relative_path = f"sounds/{final_filename}"
            return jsonify({
                "id": relative_path,
                "name": final_filename,
                "type": "custom",
                "file_path": relative_path
            })
        else:
            # For specific sound assignments, use the old logic
            safe_filename = werkzeug.utils.secure_filename(f"{sound_type}{file_ext}")
            file_path = os.path.join(SOUNDS_DIR, safe_filename)

            # Save file
            file.save(file_path)

            # Update database with relative path
            relative_path = f"sounds/{safe_filename}"
            updated = store.update_sound_setting(
                sound_type=sound_type,
                file_path=relative_path
            )

            return jsonify(updated)
    except Exception as error:
        app.logger.exception("Failed to upload sound file")
        return jsonify({"error": str(error)}), 500

@app.route("/api/sounds/test", methods=["POST"])
@requires_auth
def test_sound():
    """Test sound playback (returns file info for frontend testing)."""
    payload = request.get_json(force=True, silent=True) or {}
    sound_type = payload.get("sound_type")

    if not sound_type or sound_type not in ["break_start", "break_end"]:
        return jsonify({"error": "Invalid sound type"}), 400

    try:
        sound_setting = store.get_sound_setting(sound_type)
        if not sound_setting:
            return jsonify({"error": "Sound setting not found"}), 404

        if not sound_setting.get("enabled") or not sound_setting.get("file_path"):
            return jsonify({"error": "Sound is disabled or no file is configured"}), 400

        return jsonify({
            "sound_type": sound_type,
            "file_path": sound_setting["file_path"],
            "volume": sound_setting["volume"],
            "enabled": sound_setting["enabled"]
        })
    except Exception as error:
        app.logger.exception("Failed to test sound")
        return jsonify({"error": str(error)}), 500

@app.route("/api/sounds/delete", methods=["DELETE"])
@requires_auth
def delete_sound():
    """Delete a custom sound file."""
    payload = request.get_json(force=True, silent=True) or {}
    file_path = payload.get("file_path")

    if not file_path:
        return jsonify({"error": "File path is required"}), 400

    # Don't allow deletion of default sounds
    if file_path in ["break-start.mp3", "break-end.mp3"]:
        return jsonify({"error": "Cannot delete default sounds"}), 400

    try:
        # Construct full file path
        if file_path.startswith("sounds/"):
            filename = file_path[7:]  # Remove "sounds/" prefix
        else:
            filename = file_path

        full_path = os.path.join(SOUNDS_DIR, filename)

        # Check if file exists and delete it
        if os.path.exists(full_path):
            os.remove(full_path)
            return jsonify({"status": "deleted", "file_path": file_path})
        else:
            return jsonify({"error": "File not found"}), 404

    except Exception as error:
        app.logger.exception("Failed to delete sound file")
        return jsonify({"error": str(error)}), 500

@app.route("/sounds/<filename>")
def serve_sound(filename):
    """Serve sound files from both backend/sounds/ and frontend/ directories."""
    # First try to serve from backend/sounds/ (custom uploaded sounds)
    backend_path = os.path.join(SOUNDS_DIR, filename)
    if os.path.exists(backend_path):
        return send_from_directory(SOUNDS_DIR, filename)

    # If not found in backend, try frontend/ (default sounds)
    frontend_path = os.path.join(BASE_DIR, "frontend", filename)
    if os.path.exists(frontend_path):
        return send_from_directory(os.path.join(BASE_DIR, "frontend"), filename)

    # If not found anywhere, return 404
    return jsonify({"error": "Sound file not found"}), 404


@app.route("/api/sounds/library", methods=["GET"])
@requires_auth
def get_sound_library():
    """Get all available sounds for the library (defaults and uploaded)."""
    try:
        # Get current sound settings
        current_settings = {}
        for sound in store.get_sound_settings():
            current_settings[sound["sound_type"]] = sound

        # Get uploaded sound files
        uploaded_sounds = []
        if os.path.exists(SOUNDS_DIR):
            for filename in os.listdir(SOUNDS_DIR):
                if filename.lower().endswith(('.mp3', '.wav')):
                    file_path = f"sounds/{filename}"
                    # Check if this file is being used by any sound type
                    used_by = []
                    for sound_type, settings in current_settings.items():
                        if settings.get("file_path") == file_path:
                            used_by.append(sound_type)

                    uploaded_sounds.append({
                        "id": file_path,
                        "name": filename,
                        "type": "custom",
                        "file_path": file_path,
                        "used_by": used_by
                    })

        # Default sounds - always include these, they're guaranteed to exist in frontend/
        default_sounds = [
            {
                "id": "break-start.mp3",
                "name": "Pause beginnen (Standard)",
                "type": "default",
                "file_path": "break-start.mp3",
                "used_by": []
            },
            {
                "id": "break-end.mp3",
                "name": "Pause beenden (Standard)",
                "type": "default",
                "file_path": "break-end.mp3",
                "used_by": []
            }
        ]

        # Mark which sounds are currently used
        all_sounds = default_sounds + uploaded_sounds
        for sound in all_sounds:
            for sound_type, settings in current_settings.items():
                if settings.get("file_path") == sound["file_path"]:
                    if sound_type not in sound["used_by"]:
                        sound["used_by"].append(sound_type)

        return jsonify({
            "sounds": all_sounds,
            "current_settings": current_settings
        })
    except Exception as error:
        app.logger.exception("Failed to get sound library")
        return jsonify({"error": str(error)}), 500

@app.route("/api/public/sounds")
def get_public_sound_settings():
    """Get sound settings for public access (no auth required)."""
    try:
        sounds = store.get_sound_settings()
        # Only return enabled sounds with file paths
        public_sounds = {}
        for sound in sounds:
            if sound.get("enabled") and sound.get("file_path"):
                public_sounds[sound["sound_type"]] = {
                    "file_path": sound["file_path"],
                    "volume": sound["volume"]
                }
        return jsonify(public_sounds)
    except Exception as error:
        app.logger.exception("Failed to get public sound settings")
        return jsonify({}), 500

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
