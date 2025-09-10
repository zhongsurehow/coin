#!/bin/sh

# Exit on error
set -e

# Wait for database and cache to be ready
/app/wait-for-it.sh postgres 5432
/app/wait-for-it.sh redis 6379

echo "Dependencies are ready."

# Execute the main command
exec "$@"
