#!/bin/bash -p

set -euo pipefail

PATH=/usr/bin:/bin
export PATH

unset BASH_ENV ENV
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONOPTIMIZE
unset PYTHONWARNINGS PYTHONBREAKPOINT PYTHONUSERBASE PYTHONSAFEPATH
unset __PYVENV_LAUNCHER__
unset RAKUTEN_WEB_SERVICE_APPLICATION_ID RAKUTEN_WEB_SERVICE_ACCESS_KEY
unset RAKUTEN_AFFILIATE_ID HTTPS_PROXY HTTP_PROXY ALL_PROXY NO_PROXY
unset https_proxy http_proxy all_proxy no_proxy
unset BROWSER SSL_CERT_FILE SSL_CERT_DIR SSLKEYLOGFILE
unset LD_PRELOAD LD_LIBRARY_PATH

LC_ALL=C
export LC_ALL
umask 077

launcher_invalid() {
  printf '%s\n' '{"command":"invalid","ok":false,"reason_code":"RAKUTEN_CREDENTIAL_LAUNCHER_INVALID","status":"INVALID"}'
  exit 69
}

require_metadata() {
  local path=$1
  local expected_type=$2
  local owner_policy=$3
  local executable=${4:-false}
  local metadata mode_hex owner mode_value type_value

  metadata=$(/usr/bin/stat -c '%f %u' -- "$path" 2>/dev/null) || launcher_invalid
  read -r mode_hex owner <<<"$metadata"
  [[ $mode_hex =~ ^[0-9a-f]+$ && $owner =~ ^[0-9]+$ ]] || launcher_invalid
  mode_value=$((16#$mode_hex))
  type_value=$((mode_value & 16#f000))
  case "$expected_type" in
    directory)
      ((type_value == 16#4000)) || launcher_invalid
      ;;
    regular)
      ((type_value == 16#8000)) || launcher_invalid
      ;;
    symlink)
      ((type_value == 16#a000)) || launcher_invalid
      ;;
    *)
      launcher_invalid
      ;;
  esac
  if [[ $owner_policy == current ]]; then
    ((owner == effective_uid)) || launcher_invalid
  elif [[ $owner_policy == root-or-current ]]; then
    ((owner == 0 || owner == effective_uid)) || launcher_invalid
  else
    launcher_invalid
  fi
  if [[ $expected_type != symlink ]]; then
    (( (mode_value & 8#022) == 0 )) || launcher_invalid
  fi
  if [[ $executable == true ]]; then
    (( (mode_value & 8#100) != 0 )) || launcher_invalid
  elif [[ $executable != false ]]; then
    launcher_invalid
  fi
}

require_secure_ancestors() {
  local path=$1
  local remainder prefix index
  local -a components

  [[ $path == /* ]] || launcher_invalid
  require_metadata / directory root-or-current
  remainder=${path#/}
  IFS=/ read -r -a components <<<"$remainder"
  prefix=
  for ((index = 0; index + 1 < ${#components[@]}; index++)); do
    [[ -n ${components[index]} ]] || launcher_invalid
    prefix=$prefix/${components[index]}
    require_metadata "$prefix" directory root-or-current
  done
}

require_secure_path() {
  local path=$1
  local expected_type=$2
  local owner_policy=$3
  local executable=${4:-false}

  require_secure_ancestors "$path"
  require_metadata "$path" "$expected_type" "$owner_policy" "$executable"
}

if [[ $# -ne 1 || ( $1 != setup && $1 != check ) ]]; then
  printf '%s\n' '{"command":"invalid","ok":false,"reason_code":"RAKUTEN_CREDENTIAL_ARGUMENT_INVALID","status":"INVALID"}'
  exit 64
fi

script_directory=$(CDPATH= cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}" 2>/dev/null)" 2>/dev/null && pwd -P)
repository_root=$(CDPATH= cd -- "$script_directory/.." 2>/dev/null && pwd -P)
expected_repository_root=/home/minami/rakuten
expected_base=/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu
launcher_path=$script_directory/rakuten_live_smoke_credentials_python.sh
credential_script=$script_directory/rakuten_live_smoke_credentials.py
venv_root=$repository_root/.venv
venv_python=$venv_root/bin/python
venv_config=$venv_root/pyvenv.cfg
expected_python=$expected_base/bin/python3.14
expected_lib=$expected_base/lib
expected_stdlib=$expected_lib/python3.14
effective_uid=$(/usr/bin/id -u 2>/dev/null) || launcher_invalid

[[ $effective_uid =~ ^[0-9]+$ ]] || launcher_invalid
[[ $repository_root == "$expected_repository_root" ]] || launcher_invalid
[[ ${BASH_SOURCE[0]} == "$launcher_path" ]] || launcher_invalid

require_secure_path "$repository_root" directory current
require_secure_path "$script_directory" directory current
require_secure_path "$launcher_path" regular current true
require_secure_path "$credential_script" regular current
require_secure_path "$venv_root" directory current
require_secure_path "$venv_root/bin" directory current
require_secure_path "$venv_config" regular current
require_secure_ancestors "$venv_python"
require_metadata "$venv_python" symlink current
readlink_target_with_sentinel=$(
  /usr/bin/readlink -n -- "$venv_python" 2>/dev/null && printf '\034'
) || launcher_invalid
[[ $readlink_target_with_sentinel == "$expected_python"$'\034' ]] || launcher_invalid
require_secure_path "$expected_base" directory current
require_secure_path "$expected_base/bin" directory current
require_secure_path "$expected_python" regular current true
require_secure_path "$expected_lib" directory current
require_secure_path "$expected_stdlib" directory current

[[ ! -e $expected_lib/python314.zip && ! -L $expected_lib/python314.zip ]] || launcher_invalid
for path_configuration_directory in \
  "$venv_root/bin" "$expected_base/bin" "$expected_lib"; do
  for path_configuration_name in \
    python._pth python3.14._pth libpython3.14._pth pybuilddir.txt; do
    [[ ! -e $path_configuration_directory/$path_configuration_name \
      && ! -L $path_configuration_directory/$path_configuration_name ]] \
      || launcher_invalid
  done
done
for loader_namespace in glibc-hwcaps tls haswell avx512_1 x86_64; do
  [[ ! -e $expected_lib/$loader_namespace && ! -L $expected_lib/$loader_namespace ]] \
    || launcher_invalid
done
rpath_shadow=$(
  /usr/bin/find "$expected_lib" -xdev \
    \( -name libpthread.so.0 -o -name libdl.so.2 -o -name libutil.so.1 \
      -o -name librt.so.1 -o -name libm.so.6 -o -name libc.so.6 \) \
    -print -quit 2>/dev/null
) || launcher_invalid
[[ -z $rpath_shadow ]] || launcher_invalid

stdlib_invalid=$(
  /usr/bin/find "$expected_stdlib" -xdev \
    \( ! \( -type d -o -type f \) \
      -o \( ! -uid "$effective_uid" ! -uid 0 \) \
      -o -perm /022 \) \
    -print -quit 2>/dev/null
) || launcher_invalid
[[ -z $stdlib_invalid ]] || launcher_invalid

cd -- "$repository_root" 2>/dev/null || launcher_invalid
exec "$venv_python" -I -S - \
  "$repository_root" "$expected_base" "$venv_python" \
  "$venv_config" "$credential_script" "$1" <<'PY'
import os
import stat
import sys

INVALID = (
    b'{"command":"invalid","ok":false,'
    b'"reason_code":"RAKUTEN_CREDENTIAL_LAUNCHER_INVALID",'
    b'"status":"INVALID"}\n'
)


def fail() -> None:
    offset = 0
    while offset < len(INVALID):
        written = os.write(1, INVALID[offset:])
        if written <= 0:
            break
        offset += written
    os._exit(69)


def secure_regular(metadata: os.stat_result, effective_uid: int) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == effective_uid
        and stat.S_IMODE(metadata.st_mode) & 0o022 == 0
    )


def read_bound_regular(path: str, effective_uid: int, maximum: int) -> bytes:
    before = os.lstat(path)
    if not secure_regular(before, effective_uid):
        raise OSError
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        after = os.fstat(descriptor)
        current = os.lstat(path)
        identity = (after.st_dev, after.st_ino)
        if (
            not secure_regular(after, effective_uid)
            or identity != (before.st_dev, before.st_ino)
            or identity != (current.st_dev, current.st_ino)
            or after.st_size != before.st_size
            or after.st_size < 1
            or after.st_size > maximum
        ):
            raise OSError
        chunks = bytearray()
        while len(chunks) <= maximum:
            chunk = os.read(descriptor, min(4096, maximum + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        if len(chunks) != after.st_size or len(chunks) > maximum:
            raise OSError
        return bytes(chunks)
    finally:
        os.close(descriptor)


try:
    if len(sys.argv) != 7:
        raise OSError
    repository_root = sys.argv[1]
    expected_base = sys.argv[2]
    venv_python = sys.argv[3]
    venv_config = sys.argv[4]
    credential_script = sys.argv[5]
    command = sys.argv[6]
    effective_uid = os.geteuid()
    expected_cfg = (
        f"home = {expected_base}/bin\n"
    "implementation = CPython\n"
    "uv = 0.12.1\n"
    "version_info = 3.14.6\n"
    "include-system-site-packages = false\n"
    "prompt = raos\n"
    ).encode("utf-8")
    expected_path = [
        f"{expected_base}/lib/python314.zip",
        f"{expected_base}/lib/python3.14",
        f"{expected_base}/lib/python3.14/lib-dynload",
    ]
    valid = (
        command in {"setup", "check"}
        and sys.version_info[:3] == (3, 14, 6)
        and sys.executable == venv_python
        and sys._base_executable == f"{expected_base}/bin/python3.14"
        and sys.prefix == f"{repository_root}/.venv"
        and sys.base_prefix == expected_base
        and sys.flags.isolated == 1
        and sys.flags.no_site == 1
        and sys.flags.safe_path is True
        and sys.path == expected_path
        and os.getcwd() == repository_root
        and read_bound_regular(venv_config, effective_uid, 1024) == expected_cfg
    )
    if not valid:
        raise OSError

    before = os.lstat(credential_script)
    if not secure_regular(before, effective_uid) or before.st_nlink != 1:
        raise OSError
    script_descriptor = os.open(
        credential_script,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    after = os.fstat(script_descriptor)
    current = os.lstat(credential_script)
    identity = (after.st_dev, after.st_ino)
    if (
        not secure_regular(after, effective_uid)
        or after.st_nlink != 1
        or identity != (before.st_dev, before.st_ino)
        or identity != (current.st_dev, current.st_ino)
        or after.st_size != before.st_size
        or after.st_size < 1
        or os.stat(f"/proc/self/fd/{script_descriptor}").st_ino != after.st_ino
        or os.stat(f"/proc/self/fd/{script_descriptor}").st_dev != after.st_dev
    ):
        raise OSError
    os.set_inheritable(script_descriptor, True)
    if not os.get_inheritable(script_descriptor):
        raise OSError
    os.execve(
        venv_python,
        [
            venv_python,
            "-I",
            "-S",
            f"/proc/self/fd/{script_descriptor}",
            command,
        ],
        {"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
except BaseException:
    fail()
PY
