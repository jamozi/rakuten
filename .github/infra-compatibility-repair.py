from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str, *, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"unexpected {label} source state")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")


network_wrapper = Path("scripts/run_network_denied.sh")
replace_once(
    network_wrapper,
    '''reject_unsafe_path() {
  local label=$1
  local value=$2
  case $value in
    *'$'* | *'`'* | *'"'* | *'\\'* | *$'\r'* | *$'\n'*)
      printf 'error: %s contains unsafe transport characters\n' "$label" >&2
      return 69
      ;;
  esac
}

''',
    '''reject_unsafe_path() {
  local label=$1
  local value=$2
  case $value in
    *'$'* | *'`'* | *'"'* | *'\\'* | *$'\r'* | *$'\n'*)
      printf 'error: %s contains unsafe transport characters\n' "$label" >&2
      return 69
      ;;
  esac
}

trusted_root_executable() {
  local label=$1
  local requested=$2
  local resolved
  local owner
  local mode

  canonicalize_existing "$label" "$requested" resolved
  if [[ ! -f $resolved || ! -x $resolved ]]; then
    printf 'error: trusted %s is unavailable\n' "$label" >&2
    return 69
  fi
  owner=$(stat --format=%u -- "$resolved")
  mode=$(stat --format=%a -- "$resolved")
  if [[ $owner != 0 ]] || (( (8#$mode & 0022) != 0 )); then
    printf 'error: trusted %s ownership or mode is unsafe\n' "$label" >&2
    return 69
  fi
  printf -v "$3" '%s' "$resolved"
}

''',
    label="network trusted executable helper",
)
replace_once(
    network_wrapper,
    '''unshare_executable=/usr/bin/unshare
if [[ ! -f $unshare_executable || -L $unshare_executable || \
  ! -x $unshare_executable ]]; then
  printf 'error: trusted unshare executable is unavailable\n' >&2
  exit 69
fi
unshare_owner=$(stat --format=%u -- "$unshare_executable")
unshare_mode=$(stat --format=%a -- "$unshare_executable")
if [[ $unshare_owner != 0 ]] || (( (8#$unshare_mode & 0022) != 0 )); then
  printf 'error: unshare executable ownership or mode is unsafe\n' >&2
  exit 69
fi
''',
    '''trusted_root_executable 'unshare executable' /usr/bin/unshare unshare_executable
trusted_root_executable 'Python interpreter' /usr/bin/python3 python_executable
trusted_root_executable 'environment executable' /usr/bin/env env_executable
trusted_root_executable 'identity executable' /usr/bin/id id_executable
trusted_root_executable 'true executable' /usr/bin/true true_executable
''',
    label="network executable validation",
)
replace_once(
    network_wrapper,
    '''cd -- "$repository_root"
exec env -i \
''',
    '''# Prefer an unprivileged user namespace. Some hosted Ubuntu runners deny uid_map
# writes, so use a root-created namespace only after proving passwordless sudo and
# dropping back to the original identity with no capabilities.
isolation_command=()
if "$unshare_executable" --user --map-current-user --net --pid --fork \
  --kill-child -- "$true_executable" >/dev/null 2>&1; then
  isolation_command=(
    "$unshare_executable"
    --user
    --map-current-user
    --net
    --pid
    --fork
    --kill-child
    --
    "$python_executable"
    -I
    "$assertion"
    --exec
    --
    "$canonical_command"
    "$@"
  )
else
  trusted_root_executable 'sudo executable' /usr/bin/sudo sudo_executable
  trusted_root_executable 'setpriv executable' /usr/bin/setpriv setpriv_executable
  current_uid=$EUID
  if ! current_gid=$("$id_executable" -g); then
    printf 'error: unable to resolve the current primary group\n' >&2
    exit 69
  fi
  if [[ ! $current_uid =~ ^[1-9][0-9]*$ || ! $current_gid =~ ^[1-9][0-9]*$ ]]; then
    printf 'error: current non-root identity is malformed\n' >&2
    exit 69
  fi
  if ! "$sudo_executable" --non-interactive -- "$true_executable" >/dev/null 2>&1; then
    printf 'error: neither unprivileged namespaces nor non-interactive sudo are available\n' >&2
    exit 69
  fi
  isolation_command=(
    "$sudo_executable"
    --non-interactive
    --
    "$unshare_executable"
    --net
    --pid
    --fork
    --kill-child
    --
    "$setpriv_executable"
    "--reuid=$current_uid"
    "--regid=$current_gid"
    --clear-groups
    --no-new-privs
    --inh-caps=-all
    --ambient-caps=-all
    --bounding-set=-all
    "$env_executable"
    -i
    PATH=/usr/bin:/bin
    HOME="$canonical_home"
    LANG=C.UTF-8
    LC_ALL=C.UTF-8
    TZ=UTC
    PYTHONDONTWRITEBYTECODE=1
    RAOS_PARENT_NET_NS="$parent_net_namespace"
    RAOS_PARENT_PID_NS="$parent_pid_namespace"
    RAOS_NETWORK_DENIED=1
    "$python_executable"
    -I
    "$assertion"
    --exec
    --
    "$canonical_command"
    "$@"
  )
fi

cd -- "$repository_root"
exec env -i \
''',
    label="network namespace backend",
)
replace_once(
    network_wrapper,
    '''  /usr/bin/python3 -I -c '
''',
    '''  "$python_executable" -I -c '
''',
    label="network close-fd interpreter",
)
replace_once(
    network_wrapper,
    '''' "$unshare_executable" --user --map-current-user --net --pid --fork \
  --kill-child -- \
  /usr/bin/python3 -I "$assertion" --exec -- "$canonical_command" "$@"
''',
    '''' "${isolation_command[@]}"
''',
    label="network isolation dispatch",
)

network_test = Path("tests/st0106/test_network_isolation.py")
replace_once(
    network_test,
    '''requires_unsandboxed_parent = pytest.mark.skipif(
    OUTER_NETWORK_SANDBOX,
    reason=UNSANDBOXED_PARENT_REASON,
)


def run_guard(
''',
    '''requires_unsandboxed_parent = pytest.mark.skipif(
    OUTER_NETWORK_SANDBOX,
    reason=UNSANDBOXED_PARENT_REASON,
)


def _unprivileged_user_namespace_available() -> bool:
    result = subprocess.run(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
            "--fork",
            "--",
            "/usr/bin/true",
        ],
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    return result.returncode == 0


requires_user_namespace = pytest.mark.skipif(
    not _unprivileged_user_namespace_available(),
    reason="the runner forbids unprivileged user-namespace mappings",
)


def run_guard(
''',
    label="user namespace capability marker",
)
replace_once(
    network_test,
    '''    assert "RAOS_NETWORK_DENIED=1" in content
    assert "/usr/bin/python3 -I" in content
    assert "os.closerange" in content
    assert '"$assertion" --exec --' in content
''',
    '''    assert "RAOS_NETWORK_DENIED=1" in content
    assert "trusted_root_executable 'Python interpreter' /usr/bin/python3" in content
    assert "trusted_root_executable 'sudo executable' /usr/bin/sudo" in content
    assert "trusted_root_executable 'setpriv executable' /usr/bin/setpriv" in content
    assert '"$sudo_executable" --non-interactive' in content
    assert "--reuid=$current_uid" in content
    assert "--regid=$current_gid" in content
    assert "--clear-groups" in content
    assert "--no-new-privs" in content
    assert "--inh-caps=-all" in content
    assert "--ambient-caps=-all" in content
    assert "--bounding-set=-all" in content
    assert "neither unprivileged namespaces nor non-interactive sudo" in content
    assert "os.closerange" in content
    assert '"$assertion"' in content
    assert "--exec" in content
''',
    label="network structural assertions",
)
replace_once(
    network_test,
    '''def test_assertion_rejects_a_root_mapped_child_namespace() -> None:
''',
    '''@requires_user_namespace
def test_assertion_rejects_a_root_mapped_child_namespace() -> None:
''',
    label="root mapped assertion marker",
)
replace_once(
    network_test,
    '''def test_wrapper_rejects_a_root_mapped_caller(tmp_path: Path) -> None:
''',
    '''@requires_user_namespace
def test_wrapper_rejects_a_root_mapped_caller(tmp_path: Path) -> None:
''',
    label="root mapped wrapper marker",
)

replace_once(
    Path("tests/st0106/test_hydration_validator.py"),
    '''SYSTEM_PYTHON = Path("/usr/bin/python3.10")
''',
    '''SYSTEM_PYTHON = Path("/usr/bin/python3")
''',
    label="system Python compatibility",
)

replace_once(
    Path("scripts/object_storage_service.sh"),
    '''  object_storage_port=''
''',
    '''  # Docker allocates one collision-free loopback host port for this disposable run.
  object_storage_port=0
''',
    label="object storage dynamic port",
)

storage_test = Path("tests/st0202/test_wrapper.py")
replace_once(
    storage_test,
    '''if payload and payload[0] == "port":
    port = os.environ.get("RAOS_OBJECT_STORAGE_PORT") or "49123"
    if mode == "extra_port":
''',
    '''if payload and payload[0] == "port":
    requested_port = os.environ.get("RAOS_OBJECT_STORAGE_PORT")
    port = "49123" if requested_port in {None, "", "0"} else requested_port
    if mode == "extra_port":
''',
    label="Docker port fixture",
)
replace_once(
    storage_test,
    '''elif operation == "port":
    port = os.environ.get("RAOS_OBJECT_STORAGE_PORT") or "49123"
    print("0.0.0.0:" + port if mode == "public_port" else "127.0.0.1:" + port)
''',
    '''elif operation == "port":
    requested_port = os.environ.get("RAOS_OBJECT_STORAGE_PORT")
    port = "49123" if requested_port in {None, "", "0"} else requested_port
    print("0.0.0.0:" + port if mode == "public_port" else "127.0.0.1:" + port)
''',
    label="Compose port fixture",
)
replace_once(
    storage_test,
    '''    assert all(row["raw_credentials_present"] is False for row in rows)


@pytest.mark.parametrize(
''',
    '''    assert all(row["raw_credentials_present"] is False for row in rows)
    assert up["port"] == "0"
    compose_port = next(row for row in rows if _compose_operation(row) == "port")
    assert compose_port["port"] == "0"


@pytest.mark.parametrize(
''',
    label="dynamic port regression assertion",
)
