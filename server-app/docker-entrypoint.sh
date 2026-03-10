#!/bin/sh
set -e

if [ ! -f /data/resources.json ]; then
  echo "Seeding /data/resources.json from defaults..."
  cp /defaults/resources.json /data/resources.json
fi

exec "$@"
