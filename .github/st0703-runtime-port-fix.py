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
  if ! published_port=$(
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
if not isinstance(bindings, list) or len(bindings) != 1:
    raise SystemExit(1)
for exposed_port, exposed_bindings in ports.items():
    if exposed_port == "8333/tcp":
        continue
    if exposed_bindings not in (None, []):
        raise SystemExit(1)
binding = bindings[0]
if not isinstance(binding, dict):
    raise SystemExit(1)
if set(binding) != {"HostIp", "HostPort"}:
    raise SystemExit(1)
if binding["HostIp"] != "127.0.0.1":
    raise SystemExit(1)
host_port = binding["HostPort"]
if not isinstance(host_port, str) or not host_port.isdecimal():
    raise SystemExit(1)
port = int(host_port, 10)
if not 1024 <= port <= 65535:
    raise SystemExit(1)
print(port)
'
  ); then
    error 'the S3 endpoint is not published on one bounded loopback port'
    return 1
  fi
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
