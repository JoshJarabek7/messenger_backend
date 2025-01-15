#!/bin/bash

# Function to test if postgres is ready
postgres_ready() {
python << END
import sys
import psycopg2
import os
try:
    psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )
except psycopg2.OperationalError:
    sys.exit(-1)
sys.exit(0)
END
}

# Wait for postgres to be ready
until postgres_ready; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

>&2 echo "Postgres is up - executing command"

# # Initialize the database
# python -m app.init_db

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 