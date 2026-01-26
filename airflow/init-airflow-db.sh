#!/bin/sh
set -e

echo "Initializing Airflow database and user..."

# 1️⃣ Create airflow role (safe in SQL)
psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<EOSQL

DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${AIRFLOW_DB_USER}') THEN
      CREATE ROLE ${AIRFLOW_DB_USER}
      LOGIN
      PASSWORD '${AIRFLOW_DB_PASSWORD}';
   END IF;
END
\$\$;

EOSQL

# 2️⃣ Create airflow database ONLY if it does not exist (Alpine-safe)
DB_EXISTS=$(psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -tAc "SELECT 1 FROM pg_database WHERE datname='${AIRFLOW_DB_NAME}'")

if [ "$DB_EXISTS" != "1" ]; then
  echo "Creating Airflow database ${AIRFLOW_DB_NAME}..."
  createdb \
    --username "$POSTGRES_USER" \
    --owner "$AIRFLOW_DB_USER" \
    "$AIRFLOW_DB_NAME"
else
  echo "Airflow database already exists."
fi

echo "Airflow database initialization complete."

