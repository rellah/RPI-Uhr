# RPI-Uhr Project

A production-ready clock application with break management features, designed for deployment on Rancher.

## Features
- Real-time clock synchronization via NTP
- Dynamic break schedules backed by SQLite
- Built-in admin UI for managing breaks
- Audit trail for schedule changes
- Health monitoring endpoints
- Dockerized for easy deployment

## Requirements
- Docker 20.10+
- Docker Compose 1.29+

## Quick Start
```bash
# Build and run with Docker Compose
docker-compose up --build -d

# Access the application
open http://localhost:5000
```

## Break Administration
- Open the admin dashboard at `http://localhost:5000/admin`. The browser prompts for credentials.
- Default credentials are `admin` / `change-me`. Override via `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables.
- Use the form to add, edit, or delete breaks. All changes are validated for overlaps and stored with an audit trail.
- The display clients continue to read from `/api/config`; no Raspberry Pi changes required.

## Configuration & Persistence
- Breaks are stored in `backend/data/breaks.db` (SQLite) and created automatically if missing.
- Keep `backend/breaks.json` up to date to seed new environments. The application imports its contents only when the database is empty.
- For production deployments, mount a persistent volume at `/app/backend/data` to keep schedules across restarts (see Helm chart).

## Environment
| Variable | Description | Default |
|----------|-------------|---------|
| `ADMIN_USERNAME` | Basic auth user for admin/API writes | `admin` |
| `ADMIN_PASSWORD` | Basic auth password | `admin` |
| `ADMIN_REALM` | Browser prompt realm | `Break Administration` |
| `BREAKS_DB_PATH` | SQLite file path | `/app/backend/data/breaks.db` |
| `BREAKS_SEED_PATH` | JSON seed file | `/app/backend/breaks.json` |

## Deployment to Rancher
1. Build Docker image:
```bash
docker build -t rpi-uuhr:latest .
```

2. Push to container registry:
```bash
docker tag rpi-uuhr:latest your-registry/rpi-uuhr:latest
docker push your-registry/rpi-uuhr:latest
```

3. Create Rancher application using the following settings:
   - Image: `your-registry/rpi-uuhr:latest`
   - Port: 5000
   - Resource Limits:
     - CPU: 0.5
     - Memory: 100MB
   - Health Check:
     - Path: `/api/health`
     - Interval: 30s
   - Persistent Volume Claim:
      - Mount Path: `/app/backend/data`
      - Size: 1Gi (adjust as needed)

## Health Endpoints
- `GET /api/health`: Application health status
- `GET /api/ntp-time`: Current NTP-synchronized time

## Project Structure
```
├── backend/          # Flask application & admin UI
│   ├── data/         # SQLite persistence (gitignored)
│   ├── templates/    # Admin HTML templates
│   └── ...
├── frontend/         # Static web assets
├── Dockerfile        # Production Docker configuration
├── docker-compose.yml # Local development setup
└── .gitignore        # Version control exclusions
```

## License
MIT
