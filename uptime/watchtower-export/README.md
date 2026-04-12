# Watchtower Export Bundle

This folder is a portable package for running the uptime sync bot in Docker, alongside watchtower.

## Included Files

- Dockerfile
- docker-compose.watchtower-uptime-sync.yml
- uptime-bot.py
- requirements.txt
- config.yml
- container-monitor-map.yaml

## Create Export Tarball

From uptime-updates directory:

```bash
bash export-watchtower-bundle.sh
```

This creates a timestamped tar.gz in this folder.

## Run With Docker Compose

In this folder:

```bash
docker compose -f docker-compose.watchtower-uptime-sync.yml up -d --build
```

## Notes

- The bot uses Docker host API endpoints listed in container-monitor-map.yaml.
- Keep config.yml and container-monitor-map.yaml updated with your real values.
- This deployment does not require systemd.
