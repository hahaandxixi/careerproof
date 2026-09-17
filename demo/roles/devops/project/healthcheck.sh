#!/bin/bash
set -eu
curl --fail --max-time 3 "$HEALTH_URL"
systemctl is-active demo.service
