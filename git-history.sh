#!/bin/sh
git-history file timetrack.db timetrack.json \
  --namespace timetrack \
  --convert 'json.loads(content)'
