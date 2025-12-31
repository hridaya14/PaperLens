#!/bin/sh
set -e

echo "Waiting for database..."
python - <<EOF
import time
import os
from sqlalchemy import create_engine

url = os.environ["POSTGRES_DATABASE_URL"]
for _ in range(30):
    try:
        engine = create_engine(url)
        with engine.connect():
            print("Database ready")
            break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("Database not ready")
EOF

echo "Running migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
