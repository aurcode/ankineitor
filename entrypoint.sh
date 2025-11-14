#!/bin/sh
# Set ownership for the logs directory to appuser.
# This ensures the app can write to the log file even when the directory is mounted as a volume.
chown -R appuser:appuser /app/logs

# Execute the command passed to the script (the original CMD)
exec "$@"
