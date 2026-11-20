# Deployment

Docker Compose deployment on a Google Cloud Compute Engine VM, everyday
commands, migration from a manually created container, and a local Compose test.

For Google Cloud Compute Engine, use an Ubuntu VM with Docker Engine and the
Docker Compose plugin installed. The VM needs outbound internet access; no bot
ports or additional inbound firewall rules are required. Enable Docker at boot:

```sh
sudo systemctl enable --now docker
docker compose version
```

The commands below assume your user can run Docker. Compose builds the existing
Python slim Dockerfile, runs service `bot` as container `discord-bot`, and reads
`.env` at runtime. The image runs as UID 10001. Secrets and runtime files remain
excluded from the build context.

### Initial deployment

If `discord-bot` already exists, use the migration instructions below first.

```sh
git clone https://github.com/Risa-Miura/discord-notification-bot.git
cd discord-notification-bot
# Create .env only if it does not already exist; never overwrite existing secrets.
(umask 077; test -e .env || cp .env.example .env)
chmod 600 .env
nano .env
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Fill in the real credentials directly on the VM. Never commit `.env`.
Use `config --quiet` for validation: plain `docker compose config` can print
resolved secrets.

The named volume `discord-notification-bot_bot-data` stores role settings and
announcement history at `/data`. Compose overrides `DATA_DIR` to this location.
On a fresh installation, a server administrator should run `/set-channel` and `/set-role`
in Discord. Keep only one bot instance
running to avoid duplicate alerts.

### Future updates and everyday commands

Once these Compose files are committed and pushed to GitHub, update the VM with:

```sh
git pull
docker compose up -d --build
```

```sh
docker compose logs -f       # Follow logs; Ctrl+C only stops following
docker compose ps           # Check status
docker compose restart      # Restart the existing service
docker compose down         # Stop and remove the Compose container/network
```

`up -d` runs in the background. `restart: unless-stopped` restarts the container
after crashes and Docker/VM restarts, unless you explicitly stopped it.
After `down`, run `up -d` to start it again.
Use `up -d --build` after code or environment changes; `restart` does not load
a changed `.env`.

Normal `down` preserves the named volume and host `.env`.
**Do not add `--volumes` or `-v` to `down`: that deletes the saved bot state.**

### Migrate the existing manually created discord-bot container

Run the following in **Bash on the VM**, from the updated repository directory
with your existing `.env` present. This causes a brief outage. It builds first,
discovers the old bot's configured state path without printing secrets, backs
up its JSON files, and retains the old container as `discord-bot-manual-backup`.
Its restart policy is disabled so it cannot start alongside Compose after a reboot.

The preflight checks refuse to overwrite a previous backup container or Compose
volume. If either exists, inspect that deployment before migrating again.

```sh
(
  set -eu
  test -f .env
  docker compose config --quiet
  docker inspect --format '{{.State.Running}}' discord-bot
  if docker container inspect discord-bot-manual-backup >/dev/null 2>&1; then
    echo "Backup container already exists; stop and inspect it first."
    exit 1
  fi
  if docker volume inspect discord-notification-bot_bot-data >/dev/null 2>&1; then
    echo "Compose state volume already exists; stop and inspect it first."
    exit 1
  fi
  docker compose build
  old_data_dir=$(docker exec discord-bot python -c 'from config import load_settings; print(load_settings().data_dir)')
  test -n "$old_data_dir"
  backup_dir=$(mktemp -d "$HOME/discord-bot-state.XXXXXX")
  docker stop discord-bot
  # Missing state files are allowed for a new bot; other copy failures abort.
  for file in role_config.json youtube_state.json; do
    if ! docker cp "discord-bot:$old_data_dir/$file" "$backup_dir/$file" 2>"$backup_dir/copy-error.txt"; then
      if ! grep -q "Could not find the file" "$backup_dir/copy-error.txt"; then
        echo "State backup failed; inspect $backup_dir/copy-error.txt before continuing."
        exit 1
      fi
    fi
  done
  docker rename discord-bot discord-bot-manual-backup
  docker update --restart=no discord-bot-manual-backup
  docker compose create bot
  for file in role_config.json youtube_state.json; do
    if test -f "$backup_dir/$file"; then
      docker cp "$backup_dir/$file" "discord-bot:/data/$file"
    fi
  done
  # docker cp creates root-owned files; give the bot ownership of its new volume.
  docker compose run --rm --no-deps --user root --entrypoint chown bot -R 10001:10001 /data
  docker compose up -d --build
  docker compose ps
  printf 'State backup retained at %s\n' "$backup_dir"
)
docker compose logs -f
```

The old container must be running for the state-path discovery step. If it is
stopped, verify its state location before proceeding. If migration fails, stop
and investigate; do not start both copies. Neither your old container nor its
original volumes nor the backup directory is deleted by this procedure. The
`--rm` above removes only the short-lived ownership helper container.

To roll back after the container has been renamed:

```sh
docker compose down
docker rename discord-bot-manual-backup discord-bot
docker update --restart=unless-stopped discord-bot
docker start discord-bot
```

Rollback uses the old snapshot; alerts sent since migration may repeat. Keep the
backup container until you have verified the new service.

### Local Compose test (PowerShell)

Start Docker Desktop in Linux-container mode and use your existing `.env`.
Run only one instance using the bot token; stop any local Python copy first.
If a manual `discord-bot` container already exists locally, preserve its state
and migrate it rather than attempting to create another container with that name.

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs -f
# Press Ctrl+C to leave log following, then:
docker compose restart
docker compose ps
docker compose down
```

A fresh local Compose volume does not automatically import root-level JSON files.
Use `/set-channel` and `/set-role` to configure it, or copy the files before startup as in the
migration procedure. `/test-live` will send a real role mention.

See the [Compose service reference](https://docs.docker.com/reference/compose-file/services/)
and [volume retention on down](https://docs.docker.com/reference/cli/docker/compose/down/).
