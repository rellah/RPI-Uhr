# Builder stage for dependencies
FROM python:alpine@sha256:a94caf6aab428e086bc398beaf64a6b7a0fad4589573462f52362fd760e64cc9 AS builder
WORKDIR /app

# Install build dependencies
RUN apk update && apk add --no-cache \
    build-base \
    && rm -rf /var/cache/apk/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:alpine@sha256:a94caf6aab428e086bc398beaf64a6b7a0fad4589573462f52362fd760e64cc9
WORKDIR /app

# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Copy installed dependencies from builder
COPY --from=builder --chown=appuser:appgroup /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY --chown=appuser:appgroup backend ./backend
COPY --chown=appuser:appgroup frontend ./frontend

# Set user and permissions
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s CMD curl --fail http://localhost:5000/health || exit 1

# Expose port and run application
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "backend.wsgi:app"]