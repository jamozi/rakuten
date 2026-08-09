from pathlib import Path

path = Path("scripts/object_storage_service.sh")
text = path.read_text(encoding="utf-8")
old = "  set +e\n  published_port=$(\n"
new = (
    "  host_port_inventory=$(run_docker inspect --format "
    "'{{json .HostConfig.PortBindings}}' \"$container_id\")\n"
    "  resolved_port_inventory=$(run_docker port \"$container_id\" 8333/tcp)\n"
    "  printf 'object-storage network ports=%q\\n' \"$port_inventory\" >&2\n"
    "  printf 'object-storage host bindings=%q\\n' \"$host_port_inventory\" >&2\n"
    "  printf 'object-storage resolved port=%q\\n' \"$resolved_port_inventory\" >&2\n"
    "  set +e\n"
    "  published_port=$(\n"
)
if text.count(old) != 1:
    raise SystemExit("unexpected object-storage diagnostic insertion point")
path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")
