# RPI-Uhr Project

A production-ready clock application with break management features, designed for deployment on Rancher.

## Features
- Real-time clock synchronization via NTP
- Configurable break schedules
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

## Configuration
Edit `backend/breaks.json` to configure break schedules:
```json
{
  "breaks": [
    {"start": "10:00", "end": "10:15", "name": "Morning Break"},
    {"start": "12:00", "end": "13:00", "name": "Lunch"}
  ]
}
```

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

## Health Endpoints
- `GET /api/health`: Application health status
- `GET /api/ntp-time`: Current NTP-synchronized time

## Project Structure
```
├── backend/          # Flask application
├── frontend/         # Static web assets
├── Dockerfile        # Production Docker configuration
├── docker-compose.yml # Local development setup
└── .gitignore        # Version control exclusions
```

## License
MIT