#!/bin/sh
# Set ownership for all mounted directories to appuser.
# This ensures the app can write to all necessary files even when directories are mounted as volumes.
chown -R appuser:appuser /app/data
chown -R appuser:appuser /app/media
chown -R appuser:appuser /app/output
chown -R appuser:appuser /app/logs
chown -R appuser:appuser /app/my_audio_files
chown -R appuser:appuser /app/my_image_files

# Execute the command passed to the script as the appuser
exec gosu appuser "$@"
