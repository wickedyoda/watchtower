<p style="text-align: center; margin-left: 1.6rem;">
  <img alt="Logotype depicting a lighthouse" src="./images/logo-450px.png" width="450" />
</p>
<h1 align="center">
  Watchtower
</h1>

<p align="center">
  A container-based solution for automating Docker container base image updates.
  <br/><br/>
  <a href="https://github.com/wickedyoda/watchtower/releases">
    <img alt="latest version" src="https://img.shields.io/github/v/tag/wickedyoda/watchtower" />
  </a>
  <a href="https://github.com/wickedyoda/watchtower/blob/main/LICENSE.md">
    <img alt="Apache-2.0 License" src="https://img.shields.io/github/license/wickedyoda/watchtower.svg" />
  </a>
  <a href="https://github.com/wickedyoda/watchtower/#contributors">
    <img alt="All Contributors" src="https://img.shields.io/github/all-contributors/wickedyoda/watchtower" />
  </a>
  <a href="https://hub.docker.com/r/containrrr/watchtower">
    <img alt="Pulls from DockerHub" src="https://img.shields.io/docker/pulls/containrrr/watchtower.svg" />
  </a>
</p>

## Quick Start

With watchtower you can update the running version of your containerized app simply by pushing a new image to the Docker
Hub or your own image registry. Watchtower will pull down your new image, gracefully shut down your existing container
and restart it with the same options that were used when it was deployed initially. Run the watchtower container with
the following command:

=== "docker run"

    ```bash
    $ docker run -d \
    --name watchtower \
    -v /var/run/docker.sock:/var/run/docker.sock \
    ghcr.io/wickedyoda/watchtower:latest
    ```

=== "docker-compose.yml"

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
