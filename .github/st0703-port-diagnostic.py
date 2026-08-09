from pathlib import Path

path = Path("scripts/object_storage_service.sh")
text = path.read_text(encoding="utf-8")
old = "  set +e\n  published_port=$(\n"
new = (
    "  printf 'object-storage port inventory=%q\\n' \"$port_inventory\" >&2\n"
    "  set +e\n"
    "  published_port=$(\n"
)
if text.count(old) != 1:
    raise SystemExit("unexpected object-storage diagnostic insertion point")
path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")
