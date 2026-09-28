#!/bin/sh
# Deploy the landing page to Cloudflare: a Worker named "curia" serving docs/
# as static assets on curia.build (Cloudflare's successor to Pages). The page
# links to curia.build/github; the redirect behind it is written here, into
# the upload only, from the git remote at deploy time, so this repo never
# names the org that hosts it (the fence forbids that).
#
#   docs/deploy.sh             deploy what is in docs/ now
#
# Needs `npx wrangler login` once. The first deploy creates the Worker and the
# DNS records for the domains in `routes`.
set -eu

cd "$(dirname "$0")/.."
remote=$(git remote get-url origin)
repo=$(printf '%s\n' "$remote" | sed -E 's#^git@github\.com:#https://github.com/#; s#^ssh://git@github\.com/#https://github.com/#; s#\.git$##')
case "$repo" in
  https://github.com/*/*) ;;
  *) echo "deploy.sh: origin is not a GitHub repo ($remote)" >&2; exit 1 ;;
esac

# wrangler caches the account (its owner's name) in .wrangler/ under the
# directory it runs from, so it runs from a scratch directory, never here.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -R docs "$tmp/site"
mv "$tmp/site/worker.js" "$tmp/worker.js"
rm -f "$tmp/site/deploy.sh"
cat > "$tmp/site/_redirects" <<EOF
/github $repo 302
/github.git $repo 302
/github/* $repo/:splat 302
/github.git/* $repo.git/:splat 302
EOF
sizes=$(cd "$tmp/site" && for f in media/*; do printf '"/%s": %s, ' "$f" "$(wc -c < "$f" | tr -d ' ')"; done)
cat > "$tmp/wrangler.jsonc" <<EOF
{
  "name": "curia",
  "compatibility_date": "2026-09-15",
  "main": "./worker.js",
  "assets": { "directory": "./site", "binding": "ASSETS", "run_worker_first": ["/media/*"] },
  "vars": { "SIZES": { ${sizes%, } } },
  "routes": [
    { "pattern": "curia.build", "custom_domain": true },
    { "pattern": "www.curia.build", "custom_domain": true }
  ]
}
EOF

cd "$tmp"
npx --yes wrangler@latest deploy
