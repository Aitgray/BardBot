#!/bin/sh
set -eu

echo "[vault_sync] starting..."
echo "[vault_sync] repo=$VAULT_REPO_URL branch=$VAULT_BRANCH interval=$SYNC_INTERVAL_SECONDS"
echo "[vault_sync] tz=$TZ"
echo "[vault_sync] listing /vault before init:"
ls -la /vault || true

apk add --no-cache git openssh-client ca-certificates >/dev/null

mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Copy the mounted key into container FS so we can chmod it properly.
if [ ! -f /keys/id_ed25519 ]; then
  echo "[vault_sync] ERROR: mounted key missing at /keys/id_ed25519"
  exit 2
fi

cp /keys/id_ed25519 /root/.ssh/id_ed25519
chmod 600 /root/.ssh/id_ed25519

# known_hosts should already be mounted; verify it exists
if [ ! -f /root/.ssh/known_hosts ]; then
  echo "[vault_sync] ERROR: known_hosts missing at /root/.ssh/known_hosts"
  exit 3
fi

export GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes"

# First-time clone
if [ ! -d /vault/.git ]; then
  echo "[vault_sync] vault not initialized; cloning..."
  rm -rf /vault/*

  # Add -v for more visibility if it fails
  git clone --branch "$VAULT_BRANCH" "$VAULT_REPO_URL" /vault
  echo "[vault_sync] clone complete"
fi

# Periodic sync loop
while true; do
  echo "[vault_sync] syncing..."
  cd /vault
  git fetch --all --prune
  git reset --hard "origin/$VAULT_BRANCH"
  date -Iseconds > /vault/.last_sync
  echo "[vault_sync] sync complete; sleeping $SYNC_INTERVAL_SECONDS seconds"
  sleep "$SYNC_INTERVAL_SECONDS"
done
