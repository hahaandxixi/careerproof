#!/bin/bash
set -eu
: "${DATABASE_URL:?set isolated test URL}"
: "${BACKUP_FILE:?set output file}"
pg_dump --format=custom --file="$BACKUP_FILE" "$DATABASE_URL"
pg_restore --list "$BACKUP_FILE"
