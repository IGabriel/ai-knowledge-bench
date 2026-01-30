#!/bin/bash
# Database initialization script

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
    SELECT version();
EOSQL

echo "Database initialized with pgvector extension"
