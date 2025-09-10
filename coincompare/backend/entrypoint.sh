#!/bin/sh

# Exit on error
set -e

# Wait for database and cache to be ready
/app/wait-for-it.sh postgres 5432
/app/wait-for-it.sh redis 6379

# Run database migrations/table creation
echo "Initializing database..."
python -c "from app.database import create_tables; import asyncio; asyncio.run(create_tables())"
echo "Database initialization complete."

# Execute the main command
exec "$@"
