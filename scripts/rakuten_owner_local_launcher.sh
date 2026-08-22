#!/usr/bin/busybox sh

# Static loader-clean stage zero. No dynamic executable is started until the
# inherited environment has been replaced in full.
refuse() {
  if [ "${1-}" = doctor ]; then
    /usr/bin/busybox printf '%s\n' RAKUTEN_OWNER_LOCAL_DOCTOR_NOT_READY
  else
    /usr/bin/busybox printf '%s\n' RAKUTEN_OWNER_LOCAL_FAIL
  fi
  exit 2
}

require_metadata() {
  checked_path=$1
  checked_type=$2
  checked_owner=$3
  checked_mode=${4-}
  checked_metadata=$(
    /usr/bin/busybox stat -c '%f %u %a %h' -- "$checked_path" 2>/dev/null
  ) || refuse "${command-}"
  checked_mode_hex=${checked_metadata%% *}
  checked_remainder=${checked_metadata#* }
  checked_uid=${checked_remainder%% *}
  checked_remainder=${checked_remainder#* }
  checked_permissions=${checked_remainder%% *}
  checked_links=${checked_remainder#* }
  case "$checked_mode_hex:$checked_uid:$checked_permissions:$checked_links" in
    *[!0-9a-f:]*|'') refuse "${command-}" ;;
  esac
  checked_value=$((0x$checked_mode_hex))
  case $checked_type in
    directory) [ $((checked_value & 0xf000)) -eq 16384 ] || refuse "${command-}" ;;
    regular) [ $((checked_value & 0xf000)) -eq 32768 ] || refuse "${command-}" ;;
    *) refuse "${command-}" ;;
  esac
  if [ "$checked_owner" = root ]; then
    [ "$checked_uid" -eq 0 ] || refuse "${command-}"
  elif [ "$checked_owner" = current ]; then
    [ "$checked_uid" -eq "$effective_uid" ] || refuse "${command-}"
  elif [ "$checked_owner" = root-or-current ]; then
    { [ "$checked_uid" -eq 0 ] || [ "$checked_uid" -eq "$effective_uid" ]; } \
      || refuse "${command-}"
  else
    refuse "${command-}"
  fi
  [ $((checked_value & 18)) -eq 0 ] || refuse "${command-}"
  if [ -n "$checked_mode" ]; then
    [ "$checked_permissions" = "$checked_mode" ] || refuse "${command-}"
  fi
  if [ "$checked_type" = regular ]; then
    [ "$checked_links" -eq 1 ] || refuse "${command-}"
  fi
}

IFS=$(/usr/bin/busybox printf ' \t\n_') || refuse "${1-}"
IFS=${IFS%_}
umask 077
case "${1-}:$#" in
  setup:1|rotate:1|doctor:1|list-apis:1) ;;
  diagnose-reflection:3)
    [ "$2" = --api ] && [ "$3" = item-search ] || refuse "${1-}"
    ;;
  request:5)
    [ "$2" = --api ] && [ "$4" = --request-file ] || refuse "${1-}"
    case "$3" in item-search|product-search) ;; *) refuse "${1-}" ;; esac
    case "$5" in /*) ;; *) refuse "${1-}" ;; esac
    ;;
  smoke:3)
    [ "$2" = --api ] || refuse "${1-}"
    case "$3" in item-search|product-search) ;; *) refuse "${1-}" ;; esac
    ;;
  *) refuse "${1-}" ;;
esac
command=$1
entry_path=$0
case $entry_path in
  /home/minami/.local/share/raos/rakuten-owner-local/runtime/*/bin/rakuten-owner-local) ;;
  *) refuse "$command" ;;
esac
launcher_dir=${entry_path%/*}
runtime_root=${launcher_dir%/bin}
bundle=${runtime_root##*/}
[ "${#bundle}" -eq 64 ] || refuse "$command"
case $bundle in *[!0-9a-f]*) refuse "$command" ;; esac
expected_runtime_parent=/home/minami/.local/share/raos/rakuten-owner-local/runtime
[ "$runtime_root" = "$expected_runtime_parent/$bundle" ] || refuse "$command"
[ "$launcher_dir" = "$runtime_root/bin" ] || refuse "$command"
[ "$entry_path" = "$launcher_dir/rakuten-owner-local" ] || refuse "$command"
runtime_scripts=$runtime_root/scripts
runtime_cli=$runtime_scripts/rakuten_owner_local.py

effective_uid=$(/usr/bin/busybox id -u) || refuse "$command"
case $effective_uid in ''|*[!0-9]*) refuse "$command" ;; esac

require_metadata / directory root-or-current
require_metadata /usr directory root
require_metadata /usr/bin directory root
require_metadata /usr/bin/busybox regular root
expected_busybox_sha256=b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9
busybox_hash=$(
  /usr/bin/busybox sha256sum /usr/bin/busybox 2>/dev/null
) || refuse "$command"
[ "$busybox_hash" = "$expected_busybox_sha256  /usr/bin/busybox" ] \
  || refuse "$command"

for common_directory in \
  /home \
  /home/minami \
  /home/minami/.local \
  /home/minami/.local/share; do
  require_metadata "$common_directory" directory root-or-current
done
for private_directory in \
  /home/minami/.local/share/raos \
  /home/minami/.local/share/raos/rakuten-owner-local \
  /home/minami/.local/share/raos/rakuten-owner-local/runtime \
  "$runtime_root" \
  "$launcher_dir" \
  "$runtime_scripts"; do
  require_metadata "$private_directory" directory current 700
done
[ ! -L "$entry_path" ] || refuse "$command"
require_metadata "$entry_path" regular current 500
outer_gate_metadata=$(
  /usr/bin/busybox stat -Lc '%d %i %f %u %a %h' /proc/self/fd/4 2>/dev/null
) || refuse "$command"
entry_gate_metadata=$(
  /usr/bin/busybox stat -c '%d %i %f %u %a %h' -- "$entry_path" 2>/dev/null
) || refuse "$command"
[ "$outer_gate_metadata" = "$entry_gate_metadata" ] || refuse "$command"
exec 4<&-
[ ! -L "$runtime_cli" ] || refuse "$command"
require_metadata "$runtime_cli" regular current 400
expected_cli_sha256=b5e4646024c7b03c8381ff79876437b6d0aca772c78e4dc1976992a8383b9302
cli_hash=$(
  /usr/bin/busybox sha256sum "$runtime_cli" 2>/dev/null
) || refuse "$command"
[ "$cli_hash" = "$expected_cli_sha256  $runtime_cli" ] || refuse "$command"

python_root=/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu
python=$python_root/bin/python3.14
expected_lib=$python_root/lib
expected_stdlib=$expected_lib/python3.14
for python_directory in \
  /home/minami/.local/share/uv \
  /home/minami/.local/share/uv/python \
  "$python_root" \
  "$python_root/bin" \
  "$expected_lib" \
  "$expected_stdlib"; do
  require_metadata "$python_directory" directory current
done
require_metadata "$python" regular current 755
require_metadata "$expected_lib/libpython3.14.so.1.0" regular current 755
expected_python_sha256=c2afa8cc3c59d32bac482c122633a352c3910bfed85b59efd8ef49511d46bd2b
python_hash=$(
  /usr/bin/busybox sha256sum "$python" 2>/dev/null
) || refuse "$command"
[ "$python_hash" = "$expected_python_sha256  $python" ] || refuse "$command"

[ ! -e "$expected_lib/python314.zip" ] && [ ! -L "$expected_lib/python314.zip" ] \
  || refuse "$command"
for path_configuration_directory in "$python_root" "$python_root/bin" "$expected_lib"; do
  for path_configuration_name in \
    python._pth python3.14._pth libpython3.14._pth pybuilddir.txt pyvenv.cfg; do
    [ ! -e "$path_configuration_directory/$path_configuration_name" ] \
      && [ ! -L "$path_configuration_directory/$path_configuration_name" ] \
      || refuse "$command"
  done
done
for loader_namespace in glibc-hwcaps tls haswell avx512_1 x86_64; do
  [ ! -e "$expected_lib/$loader_namespace" ] \
    && [ ! -L "$expected_lib/$loader_namespace" ] || refuse "$command"
done
rpath_shadow=$(
  /usr/bin/busybox find "$expected_lib" -xdev \
    \( -name libpthread.so.0 -o -name libdl.so.2 -o -name libutil.so.1 \
      -o -name librt.so.1 -o -name libm.so.6 -o -name libc.so.6 \) \
    -print -quit 2>/dev/null
) || refuse "$command"
[ -z "$rpath_shadow" ] || refuse "$command"
stdlib_invalid=$(
  /usr/bin/busybox find "$expected_stdlib" -xdev \
    \( ! \( -type d -o -type f \) \
      -o \( ! -user "$effective_uid" ! -user 0 \) \
      -o -perm +022 \) \
    -print -quit 2>/dev/null
) || refuse "$command"
[ -z "$stdlib_invalid" ] || refuse "$command"

exec 3<"$entry_path" || refuse "$command"
exec /usr/bin/busybox env -i \
  PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  "$python" -B -I -S "$runtime_cli" "$@"
