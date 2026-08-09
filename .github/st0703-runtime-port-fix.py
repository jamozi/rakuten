from __future__ import annotations

from pathlib import Path


def replace_range(
    path: Path,
    *,
    start_marker: str,
    end_marker: str,
    replacement: str,
    label: str,
) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(start_marker) != 1 or text.count(end_marker) != 1:
        raise SystemExit(f"unexpected {label} source state")
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    path.write_text(
        text[:start] + replacement + text[end:],
        encoding="utf-8",
        newline="",
    )


replace_range(
    Path("scripts/object_storage_service.sh"),
    start_marker="  port_inventory=$(run_docker inspect --format ",
    end_marker="  published_port=$((10#${BASH_REMATCH[1]}))\n",
    replacement=r'''  port_inventory=$(run_docker inspect --format '{{json .NetworkSettings.Ports}}' "$container_id")
  set +e
  published_port=$(
    printf '%s' "$port_inventory" | /usr/bin/python3 -I -c '
import json
import sys

try:
    ports = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError):
    raise SystemExit(1)
if not isinstance(ports, dict):
    raise SystemExit(1)
bindings = ports.get("8333/tcp")
if not isinstance(bindings, list) or not bindings:
    raise SystemExit(1)
active_bindings = []
for binding in bindings:
    if not isinstance(binding, dict):
        raise SystemExit(1)
    if "HostIp" not in binding or "HostPort" not in binding:
        raise SystemExit(1)
    host_ip = binding["HostIp"]
    host_port = binding["HostPort"]
    if not isinstance(host_ip, str) or not isinstance(host_port, str):
        raise SystemExit(1)
    if host_port == "":
        continue
    active_bindings.append(binding)
if len(active_bindings) != 1:
    raise SystemExit(1)
for exposed_port, exposed_bindings in ports.items():
    if exposed_port == "8333/tcp" or exposed_bindings in (None, []):
        continue
    if not isinstance(exposed_bindings, list):
        raise SystemExit(2)
    if any(
        not isinstance(binding, dict)
        or not isinstance(binding.get("HostPort"), str)
        or binding.get("HostPort") != ""
        for binding in exposed_bindings
    ):
        raise SystemExit(2)
binding = active_bindings[0]
if binding["HostIp"] != "127.0.0.1":
    raise SystemExit(1)
host_port = binding["HostPort"]
if not host_port.isdecimal():
    raise SystemExit(1)
port = int(host_port, 10)
if not 1024 <= port <= 65535:
    raise SystemExit(1)
print(port)
'
  )
  port_status=$?
  set -e
  case $port_status in
    0) ;;
    2)
      error 'the object-storage container publishes an unexpected host port'
      return 1
      ;;
    *)
      error 'the S3 endpoint is not published on one bounded loopback port'
      return 1
      ;;
  esac
''',
    label="object-storage runtime port inspection",
)

replace_range(
    Path("tests/st0202/test_wrapper.py"),
    start_marker='    if ".NetworkSettings.Ports" in template:\n',
    end_marker='    elif ".Config.Image" in template:\n',
    replacement='''    if ".NetworkSettings.Ports" in template:
        port = os.environ.get("RAOS_OBJECT_STORAGE_PORT") or "49123"
        ports = {{
            "8333/tcp": [
                {{"HostIp": "127.0.0.1", "HostPort": port}},
                {{"HostIp": "::", "HostPort": ""}},
            ],
            "9333/tcp": None,
        }}
        if mode == "extra_port":
            ports["9333/tcp"] = [
                {{"HostIp": "0.0.0.0", "HostPort": "9333"}},
            ]
        elif mode == "public_port":
            ports["8333/tcp"][0]["HostIp"] = "0.0.0.0"
        print(json.dumps(ports, sort_keys=True, separators=(",", ":")))
    elif ".Config.Image" in template:
''',
    label="fake Docker runtime port inventory",
)
