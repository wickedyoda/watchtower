#!/usr/bin/env python3
"""Continuously sync Docker container IDs into Uptime Kuma docker monitors.

This bot reads:
- config.yml
- container-monitor-map.yaml

From the same directory as this script.

It reacts to Docker container lifecycle events when possible and keeps the
existing polling loop as a fallback so the mappings stay in sync even if the
event stream disconnects temporarily.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Set

import yaml
from uptime_kuma_api import UptimeKumaApi


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.getenv("UPTIME_BOT_CONFIG", os.path.join(BASE_DIR, "config.yml"))
MAP_PATH = os.getenv("UPTIME_BOT_MAP", os.path.join(BASE_DIR, "container-monitor-map.yaml"))
EVENT_RELEVANT_ACTIONS = {"create", "start", "restart", "rename"}

STOP = False


class WakeSignal:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._pending = False

    def trigger(self) -> None:
        with self._condition:
            self._pending = True
            self._condition.notify_all()

    def wait(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while True:
                if self._pending:
                    self._pending = False
                    return True

                remaining = deadline - time.monotonic()
                if remaining <= 0 or STOP:
                    return False

                self._condition.wait(min(1.0, remaining))


def _signal_handler(signum: int, _frame: Any) -> None:
    global STOP
    STOP = True
    logging.info("Received signal %s, shutting down...", signum)


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root in {path} must be a mapping")
    return data


def _normalize_docker_host_url(raw_url: str) -> str:
    if raw_url.startswith("tcp://"):
        return "http://" + raw_url[len("tcp://") :]
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    raise ValueError(f"Unsupported host_api scheme: {raw_url}")


def _normalize_container_name(name: str) -> str:
    return name.lstrip("/").strip().lower()


def _build_docker_events_url(host_api: str) -> str:
    base_url = _normalize_docker_host_url(host_api).rstrip("/")
    filters = urllib.parse.quote(json.dumps({"type": ["container"]}), safe="")
    return f"{base_url}/events?filters={filters}"


def _docker_get_container_id(host_api: str, container_name: str, timeout_seconds: int) -> Optional[str]:
    """Resolve a container name on a Docker host to its full container ID.

    Uses Docker remote API endpoint: /containers/{name}/json
    """
    base_url = _normalize_docker_host_url(host_api).rstrip("/")
    encoded_name = urllib.parse.quote(container_name, safe="")
    url = f"{base_url}/containers/{encoded_name}/json"

    request = urllib.request.Request(url=url, method="GET", headers={"Accept": "application/json"})

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            logging.warning("Container not found on host %s: %s", host_api, container_name)
            return None
        raise

    container_id = payload.get("Id")
    if not container_id:
        raise RuntimeError(f"Docker API response missing Id for {container_name} on {host_api}")
    return str(container_id)


def _extract_event_container_name(event: Dict[str, Any]) -> str:
    actor = event.get("Actor")
    if isinstance(actor, dict):
        attributes = actor.get("Attributes")
        if isinstance(attributes, dict):
            name = str(attributes.get("name") or "").strip()
            if name:
                return _normalize_container_name(name)

    name = str(event.get("name") or "").strip()
    if name:
        return _normalize_container_name(name)

    return ""


def _api_login(url: str, api_key: str) -> UptimeKumaApi:
    api = UptimeKumaApi(url)
    # Uptime Kuma API key auth in wrapper is login_by_token.
    api.login_by_token(api_key)
    return api


def _update_monitor_container_id(
    api: UptimeKumaApi,
    monitor_id: int,
    new_container_id: str,
    dry_run: bool,
) -> bool:
    """Attempt to update docker_container for a monitor.

    Returns True if monitor was updated, False if unchanged or dry-run.
    """
    monitor = api.get_monitor(monitor_id)
    if not isinstance(monitor, dict):
        raise RuntimeError(f"Unexpected monitor payload for id {monitor_id}: {type(monitor)}")

    current_id = str(monitor.get("docker_container") or "")
    if current_id == new_container_id:
        return False

    if dry_run:
        logging.info(
            "Dry-run: would update monitor %s docker_container from %s to %s",
            monitor_id,
            current_id,
            new_container_id,
        )
        return False

    last_error: Optional[Exception] = None

    # Try minimal edit call patterns first.
    for call in (
        lambda: api.edit_monitor(monitor_id, docker_container=new_container_id),
        lambda: api.edit_monitor(id=monitor_id, docker_container=new_container_id),
    ):
        try:
            call()
            logging.info(
                "Updated monitor %s docker_container from %s to %s",
                monitor_id,
                current_id,
                new_container_id,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    if last_error is None:
        raise RuntimeError(f"Failed to update monitor {monitor_id} for unknown reason")
    raise RuntimeError(f"Failed to update monitor {monitor_id}: {last_error}")


def _build_host_event_map(mappings: list[Dict[str, Any]]) -> Dict[str, Set[str]]:
    host_event_map: Dict[str, Set[str]] = {}

    for item in mappings:
        if not isinstance(item, dict):
            continue
        if item.get("enabled", True) is False:
            continue

        host_api = str(item.get("host_api") or "").strip()
        container_name = str(item.get("container_name") or "").strip()
        if not host_api or not container_name:
            continue

        host_event_map.setdefault(host_api, set()).add(_normalize_container_name(container_name))

    return host_event_map


def _watch_docker_events(
    host_api: str,
    watched_container_names: Set[str],
    wake_signal: WakeSignal,
    timeout_seconds: int,
    stop_event: threading.Event,
) -> None:
    if not watched_container_names:
        return

    request = urllib.request.Request(
        url=_build_docker_events_url(host_api),
        method="GET",
        headers={"Accept": "application/json"},
    )
    stream_timeout_seconds = max(60, timeout_seconds)

    while not stop_event.is_set() and not STOP:
        try:
            with urllib.request.urlopen(request, timeout=stream_timeout_seconds) as response:
                while not stop_event.is_set() and not STOP:
                    raw_line = response.readline()
                    if not raw_line:
                        break

                    try:
                        event = json.loads(raw_line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue

                    action = str(event.get("Action") or event.get("status") or "").strip().lower()
                    if action not in EVENT_RELEVANT_ACTIONS:
                        continue

                    container_name = _extract_event_container_name(event)
                    if container_name not in watched_container_names:
                        continue

                    logging.info(
                        "Detected Docker event %s for %s on %s",
                        action,
                        container_name,
                        host_api,
                    )
                    wake_signal.trigger()
        except Exception as exc:  # noqa: BLE001
            if stop_event.is_set() or STOP:
                return
            logging.warning("Docker event stream for %s disconnected: %s", host_api, exc)
            for _ in range(5):
                if stop_event.is_set() or STOP:
                    return
                time.sleep(1)


def _run_once(config: Dict[str, Any], mapping: Dict[str, Any]) -> None:
    uptime_cfg = config.get("uptime_kuma") or {}
    bot_cfg = config.get("bot") or {}

    uptime_url = str(uptime_cfg.get("url") or "").strip()
    api_key = str(uptime_cfg.get("api_key") or "").strip()
    dry_run = bool(bot_cfg.get("dry_run", False))
    timeout_seconds = int(bot_cfg.get("request_timeout_seconds", 10))

    if not uptime_url:
        raise ValueError("config.yml missing uptime_kuma.url")
    if not api_key or api_key == "PUT_YOUR_API_KEY_HERE":
        raise ValueError("config.yml missing real uptime_kuma.api_key")

    mappings = mapping.get("mappings") or []
    if not isinstance(mappings, list):
        raise ValueError("container-monitor-map.yaml: mappings must be a list")

    if not mappings:
        logging.info("No mappings configured. Nothing to do.")
        return

    api = _api_login(uptime_url, api_key)
    updated = 0

    try:
        for item in mappings:
            if not isinstance(item, dict):
                logging.warning("Skipping invalid mapping item (not a mapping): %r", item)
                continue

            if item.get("enabled", True) is False:
                continue

            name = str(item.get("name") or "unnamed")
            host_api = str(item.get("host_api") or "").strip()
            container_name = str(item.get("container_name") or "").strip()
            expected_type = str(item.get("expected_uptime_type") or "").strip().lower()

            monitor_id_raw = item.get("uptime_monitor_id")
            try:
                monitor_id = int(monitor_id_raw)
            except Exception as exc:  # noqa: BLE001
                logging.error("[%s] Invalid uptime_monitor_id: %r (%s)", name, monitor_id_raw, exc)
                continue

            if not host_api or not container_name:
                logging.error("[%s] Missing host_api or container_name", name)
                continue

            try:
                container_id = _docker_get_container_id(host_api, container_name, timeout_seconds)
                if not container_id:
                    continue

                monitor = api.get_monitor(monitor_id)
                monitor_type = str((monitor or {}).get("type") or "").lower()
                if expected_type and monitor_type and monitor_type != expected_type:
                    logging.error(
                        "[%s] Monitor %s type mismatch. expected=%s actual=%s",
                        name,
                        monitor_id,
                        expected_type,
                        monitor_type,
                    )
                    continue

                changed = _update_monitor_container_id(api, monitor_id, container_id, dry_run)
                if changed:
                    updated += 1
            except Exception as exc:  # noqa: BLE001
                logging.exception("[%s] Failed to process mapping: %s", name, exc)
    finally:
        try:
            api.disconnect()
        except Exception:  # noqa: BLE001
            pass

    logging.info("Cycle complete. monitors_updated=%s", updated)


def _start_event_watchers(
    mappings: list[Dict[str, Any]],
    timeout_seconds: int,
    wake_signal: WakeSignal,
) -> tuple[threading.Event, list[threading.Thread], Dict[str, Set[str]]]:
    stop_event = threading.Event()
    host_event_map = _build_host_event_map(mappings)
    threads: list[threading.Thread] = []

    for host_api, watched_container_names in host_event_map.items():
        thread = threading.Thread(
            target=_watch_docker_events,
            args=(host_api, watched_container_names, wake_signal, timeout_seconds, stop_event),
            name=f"uptime-watch-{host_api}",
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    if host_event_map:
        logging.info("Watching Docker events for %s host(s)", len(host_event_map))
    else:
        logging.info("No Docker event watchers configured")

    return stop_event, threads, host_event_map


def _stop_event_watchers(stop_event: threading.Event, threads: list[threading.Thread]) -> None:
    stop_event.set()
    for thread in threads:
        thread.join(timeout=2)


def main() -> int:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not os.path.exists(CONFIG_PATH):
        logging.error("Missing config file: %s", CONFIG_PATH)
        return 1
    if not os.path.exists(MAP_PATH):
        logging.error("Missing mapping file: %s", MAP_PATH)
        return 1

    config = _load_yaml(CONFIG_PATH)
    mapping = _load_yaml(MAP_PATH)
    bot_cfg = config.get("bot") or {}
    interval_seconds = int(bot_cfg.get("poll_interval_seconds", 60))
    if interval_seconds < 5:
        logging.warning("poll_interval_seconds too low (%s), forcing to 5", interval_seconds)
        interval_seconds = 5

    wake_signal = WakeSignal()
    event_timeout_seconds = int(bot_cfg.get("request_timeout_seconds", 10))
    stop_event, watcher_threads, host_event_map = _start_event_watchers(
        mapping.get("mappings") or [],
        event_timeout_seconds,
        wake_signal,
    )

    logging.info("Starting uptime bot. interval=%ss", interval_seconds)

    try:
        while not STOP:
            try:
                _run_once(config, mapping)
            except Exception as exc:  # noqa: BLE001
                logging.exception("Cycle failed: %s", exc)

            if STOP:
                break

            try:
                new_config = _load_yaml(CONFIG_PATH)
                new_mapping = _load_yaml(MAP_PATH)
                new_bot_cfg = new_config.get("bot") or {}
                new_interval_seconds = int(new_bot_cfg.get("poll_interval_seconds", interval_seconds))
                new_interval_seconds = max(5, new_interval_seconds)
                new_event_timeout_seconds = int(new_bot_cfg.get("request_timeout_seconds", event_timeout_seconds))
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to reload config/map, using previous values: %s", exc)
                new_config = config
                new_mapping = mapping
                new_interval_seconds = interval_seconds
                new_event_timeout_seconds = event_timeout_seconds

            new_host_event_map = _build_host_event_map(new_mapping.get("mappings") or [])
            if new_host_event_map != host_event_map or new_event_timeout_seconds != event_timeout_seconds:
                _stop_event_watchers(stop_event, watcher_threads)
                stop_event, watcher_threads, host_event_map = _start_event_watchers(
                    new_mapping.get("mappings") or [],
                    new_event_timeout_seconds,
                    wake_signal,
                )
                event_timeout_seconds = new_event_timeout_seconds

            config = new_config
            mapping = new_mapping
            interval_seconds = new_interval_seconds

            wake_signal.wait(interval_seconds)

    finally:
        _stop_event_watchers(stop_event, watcher_threads)

    logging.info("Uptime bot stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
