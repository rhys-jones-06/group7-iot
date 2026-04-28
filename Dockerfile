FROM python:3.12-slim

# OpenShift runs containers with arbitrary UIDs in group 0.
# All files must be owned/writable by group 0.
WORKDIR /app

COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY server/ ./


ENV FLASK_ENV=production \
    PORT=8080

EXPOSE 8080

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "2", \
     "--timeout", "60", \
     "--log-level", "info", \
     "wsgi:application"]
