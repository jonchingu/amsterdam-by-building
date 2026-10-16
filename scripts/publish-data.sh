#!/usr/bin/env bash
# Pack the generated web/data/ and attach it to the `data-latest` GitHub release, where the deploy workflow picks it up.
# Run after the pipeline:  scripts/publish-data.sh   (needs the gh CLI, logged in)
set -euo pipefail
cd "$(dirname "$0")/.."

# Workers static assets refuse files over 25 MiB; stop here rather than in CI.
big=$(find web/data -type f -size +25M -not -path 'web/data/tiles/*')
if [ -n "$big" ]; then
  echo "Over Cloudflare's 25 MiB per-file limit:"; echo "$big"
  echo "Raise n_packs in pipeline/s03_tiles.py (or split the file), then rerun." >&2
  exit 1
fi

tar --exclude='data/tiles' -czf web-data.tar.gz -C web data
echo "web-data.tar.gz: $(du -h web-data.tar.gz | cut -f1), $(tar -tzf web-data.tar.gz | grep -vc '/$') files"

gh release view data-latest >/dev/null 2>&1 ||
  gh release create data-latest --title "Generated web data" --notes "web/data/ from the pipeline, used by the Cloudflare deploy." --latest=false
gh release upload data-latest web-data.tar.gz --clobber
rm web-data.tar.gz
echo "Uploaded. Run the 'Deploy to Cloudflare' workflow (or push to main) to publish it."
