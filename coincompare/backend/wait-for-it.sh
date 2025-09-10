#!/bin/sh
# wait-for-it.sh: wait for a host and port to become available.

set -e

HOST="$1"
PORT="$2"
shift 2
CMD="$@"

# Check if nc (netcat) is installed
if ! command -v nc > /dev/null; then
  echo "Error: netcat is not installed. Please add it to the Dockerfile." >&2
  exit 1
fi

echo "Waiting for $HOST:$PORT..."

# Loop until we can connect
while ! nc -z "$HOST" "$PORT"; do
  sleep 1
done

echo "$HOST:$PORT is available."

# Execute the rest of the command
if [ -n "$CMD" ]; then
  exec $CMD
fi
