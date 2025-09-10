#!/bin/sh

# Exit on error
set -e

# Run database migrations/table creation
echo "Initializing database..."
python -c "from app.database import create_tables; import asyncio; asyncio.run(create_tables())"
echo "Database initialization complete."

# Execute the main command
exec "$@"
