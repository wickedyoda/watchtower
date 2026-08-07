<div align="center">
  <img src="./logo.png" width="450" />
  
# Origional Watchtower package has not been updated in a while, there is several PR and images out there which need to be applied. So, I have forked his repo here and corrected a few things. Here is a link to my repo with docker images. 

# Watchtower
  
A process for automating Docker container base image updates.

## Quick Start

With watchtower you can update the running version of your containerized app simply by pushing a new image to the Docker Hub or your own image registry. 

Watchtower will pull down your new image, gracefully shut down your existing container and restart it with the same options that were used when it was deployed initially. Run the watchtower container with the following command:

```
$ docker run --detach \
    --name watchtower \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    ghcr.io/wickedyoda/watchtower:latest
```

To run watchtower against a specific set of containers (instead of all containers), pass the container names as arguments:

```
$ docker run --detach \
    --name watchtower \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    ghcr.io/wickedyoda/watchtower:latest \
    --interval 30 nginx redis
```

### docker-compose.yml

Alternatively, you can run watchtower with Docker Compose. Create a `docker-compose.yml`:

```yaml
version: "3"
services:
  watchtower:
    image: ghcr.io/wickedyoda/watchtower:latest
    container_name: watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      WATCHTOWER_CRON_SCHEDULE: "0 0 4 * * *"
    command: --http-api-metrics --http-api-token changeme --debug
```

Then start it:

```bash
$ docker compose up -d
```

Or with the legacy Docker Compose:

```bash
$ docker-compose up -d
```

Watchtower is intended to be used in homelabs, media centers, local dev environments, and similar. We do **not** recommend using Watchtower in a commercial or production environment. If that is you, you should be looking into using Kubernetes. If that feels like too big a step for you, please look into solutions like [MicroK8s](https://microk8s.io/) and [k3s](https://k3s.io/) that take away a lot of the toil of running a Kubernetes cluster.

## Documentation
The full documentation is available at https://github.com/wickedyoda/watchtower.

## Environment File Setup

An `example.env` file is included at the repository root with all supported environment variables.

1. Copy `example.env` to `.env`
2. Fill in the values you want to use
3. Start watchtower with the env file

Example using Docker:

```bash
docker run --detach \
  --name watchtower \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --env-file .env \
  ghcr.io/wickedyoda/watchtower:latest
```

For full flag and argument behavior, see `docs/arguments.md`.

Example using Docker Compose with an env file:

```bash
docker compose --env-file .env up -d
```

