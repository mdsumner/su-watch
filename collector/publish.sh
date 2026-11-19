#!/usr/bin/env bash
# Collect SU data for every Nectar project, update data/, commit and push.
# Run daily by su-watch.timer (systemd user timer); safe to run by hand.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull -q --rebase --autostash

new=data/.su-watch.json.new
bash collector/su-watch.sh > "$new"
# only replace the published file with valid JSON that has projects in it
python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["projects"]' "$new"
mv "$new" data/su-watch.json
python3 -I collector/history.py data/su-watch.json data/history.csv

git add data/su-watch.json data/history.csv
if ! git diff --cached --quiet; then
  git commit -q -m "data $(date -u +%F)"
  git push -q
fi
