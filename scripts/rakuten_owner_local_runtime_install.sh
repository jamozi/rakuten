#!/usr/bin/busybox sh

# Credential-blind authenticated runtime installer. The documented outer
# command authenticates this complete stage through fd 4 before this body runs.
# No dynamic executable starts until this stage has replaced the environment
# and validated the root-owned OS Python trust closure.
refuse() {
  /usr/bin/busybox printf '%s\n' RAKUTEN_OWNER_LOCAL_RUNTIME_INSTALL_FAILED
  exit 2
}

require_metadata() {
  checked_path=$1
  checked_type=$2
  checked_owner=$3
  checked_mode=${4-}
  checked_metadata=$(
    /usr/bin/busybox stat -c '%f %u %a %h %s' -- "$checked_path" 2>/dev/null
  ) || refuse
  checked_mode_hex=${checked_metadata%% *}
  checked_remainder=${checked_metadata#* }
  checked_uid=${checked_remainder%% *}
  checked_remainder=${checked_remainder#* }
  checked_permissions=${checked_remainder%% *}
  checked_remainder=${checked_remainder#* }
  checked_links=${checked_remainder%% *}
  checked_size=${checked_remainder#* }
  case "$checked_mode_hex:$checked_uid:$checked_permissions:$checked_links:$checked_size" in
    *[!0-9a-f:]*|'') refuse ;;
  esac
  checked_value=$((0x$checked_mode_hex))
  case $checked_type in
    directory) [ $((checked_value & 0xf000)) -eq 16384 ] || refuse ;;
    regular) [ $((checked_value & 0xf000)) -eq 32768 ] || refuse ;;
    symlink) [ $((checked_value & 0xf000)) -eq 40960 ] || refuse ;;
    *) refuse ;;
  esac
  if [ "$checked_owner" = root ]; then
    [ "$checked_uid" -eq "$expected_root_uid" ] || refuse
  elif [ "$checked_owner" = current ]; then
    [ "$checked_uid" -eq "$effective_uid" ] || refuse
  elif [ "$checked_owner" = root-or-current ]; then
    { [ "$checked_uid" -eq "$expected_root_uid" ] \
      || [ "$checked_uid" -eq "$effective_uid" ]; } || refuse
  else
    refuse
  fi
  if [ "$checked_type" != symlink ]; then
    [ $((checked_value & 18)) -eq 0 ] || refuse
  fi
  if [ -n "$checked_mode" ]; then
    [ "$checked_permissions" = "$checked_mode" ] || refuse
  fi
  if [ "$checked_type" = regular ]; then
    [ "$checked_links" -eq 1 ] || refuse
  fi
}

require_symlink() {
  symlink_path=$1
  symlink_target=$2
  require_metadata "$symlink_path" symlink root
  observed_target=$(
    /usr/bin/busybox readlink -n -- "$symlink_path" 2>/dev/null
    /usr/bin/busybox printf '\034'
  ) || refuse
  [ "$observed_target" = "$symlink_target$(/usr/bin/busybox printf '\034')" ] \
    || refuse
}

require_absent() {
  [ ! -e "$1" ] && [ ! -L "$1" ] || refuse
}

require_root_tree() {
  tree_invalid=$(
    /usr/bin/busybox find "$1" -xdev \
      \( ! \( -type d -o -type f -o -type l \) \
        -o \( \( -type d -o -type f \) \
          \( ! -user "$expected_root_uid" -o -perm +022 \) \) \
        -o \( -type l ! -user "$expected_root_uid" \) \) \
      -print -quit 2>/dev/null
  ) || refuse
  [ -z "$tree_invalid" ] || refuse
}

require_hash() {
  hash_path=$1
  hash_value=$2
  actual_hash=$(
    /usr/bin/busybox sha256sum "$hash_path" 2>/dev/null
  ) || refuse
  [ "$actual_hash" = "$hash_value  $hash_path" ] || refuse
}

IFS=$(/usr/bin/busybox printf ' \t\n_') || refuse
IFS=${IFS%_}
umask 077
[ "$#" -eq 0 ] || refuse
expected_root_uid=0
effective_uid=$(/usr/bin/busybox id -u 2>/dev/null) || refuse
case $effective_uid in ''|*[!0-9]*) refuse ;; esac

entry_path=/home/minami/rakuten/scripts/rakuten_owner_local_runtime_install.sh
installer_path=/home/minami/rakuten/scripts/install_rakuten_owner_local_runtime.py
python_path=/usr/bin/python3.10
expected_busybox_sha256=b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9
expected_python_sha256=7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86
expected_installer_sha256=e25b742f76904f8c50db9439bc02f435bdf8076068ea0e00a0746b69bdaf60ef

require_metadata / directory root-or-current
require_metadata /usr directory root
require_metadata /usr/bin directory root
require_metadata /usr/bin/busybox regular root 755
require_hash /usr/bin/busybox "$expected_busybox_sha256"
for repository_directory in \
  /home \
  /home/minami \
  /home/minami/rakuten \
  /home/minami/rakuten/scripts; do
  require_metadata "$repository_directory" directory root-or-current
done
require_metadata "$entry_path" regular current
entry_fd_metadata=$(
  /usr/bin/busybox stat -Lc '%d %i %f %u %a %h %s' \
    /proc/self/fd/4 2>/dev/null
) || refuse
entry_named_metadata=$(
  /usr/bin/busybox stat -c '%d %i %f %u %a %h %s' -- \
    "$entry_path" 2>/dev/null
) || refuse
[ "$entry_fd_metadata" = "$entry_named_metadata" ] || refuse

# The exact root-owned Python binary is opened before hashing and later
# executed through this same descriptor, preventing pathname replacement.
require_metadata "$python_path" regular root 755
exec 5<"$python_path" || refuse
python_fd_metadata=$(
  /usr/bin/busybox stat -Lc '%d %i %f %u %a %h %s' \
    /proc/self/fd/5 2>/dev/null
) || refuse
python_named_metadata=$(
  /usr/bin/busybox stat -c '%d %i %f %u %a %h %s' -- \
    "$python_path" 2>/dev/null
) || refuse
[ "$python_fd_metadata" = "$python_named_metadata" ] || refuse
require_hash /proc/self/fd/5 "$expected_python_sha256"

# Authenticate the repository installer as data before Python parses it.
require_metadata "$installer_path" regular current
installer_size=$(
  /usr/bin/busybox stat -c '%s' -- "$installer_path" 2>/dev/null
) || refuse
case $installer_size in ''|*[!0-9]*) refuse ;; esac
[ "$installer_size" -ge 1 ] && [ "$installer_size" -le 2097152 ] || refuse
exec 6<"$installer_path" || refuse
installer_fd_metadata=$(
  /usr/bin/busybox stat -Lc '%d %i %f %u %a %h %s' \
    /proc/self/fd/6 2>/dev/null
) || refuse
installer_named_metadata=$(
  /usr/bin/busybox stat -c '%d %i %f %u %a %h %s' -- \
    "$installer_path" 2>/dev/null
) || refuse
[ "$installer_fd_metadata" = "$installer_named_metadata" ] || refuse
require_hash /proc/self/fd/6 "$expected_installer_sha256"

# The interpreter is dynamic. Its complete accepted trust class is the
# root-owned OS runtime: exact loader/config inventory, secure configured
# native-library trees, and secure stdlib with three exact distro symlinks.
require_symlink /lib usr/lib
require_symlink /lib64 usr/lib64
require_metadata /usr/lib directory root
require_metadata /usr/lib64 directory root
require_metadata /usr/lib/x86_64-linux-gnu directory root
require_metadata /usr/lib/python3.10 directory root
require_metadata /usr/lib/python3.10/lib-dynload directory root
require_symlink /usr/lib64/ld-linux-x86-64.so.2 \
  /lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
require_metadata /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 regular root 755
require_metadata /etc directory root
require_metadata /etc/ld.so.conf regular root 644
require_metadata /etc/ld.so.conf.d directory root 755
require_metadata /etc/ld.so.cache regular root 644
require_absent /etc/ld.so.preload

ld_config_inventory=$(
  /usr/bin/busybox find /etc/ld.so.conf.d -mindepth 1 -maxdepth 1 \
    -type f -print 2>/dev/null | /usr/bin/busybox sort
) || refuse
expected_ld_config_inventory='/etc/ld.so.conf.d/fakeroot-x86_64-linux-gnu.conf
/etc/ld.so.conf.d/ld.wsl.conf
/etc/ld.so.conf.d/libc.conf
/etc/ld.so.conf.d/x86_64-linux-gnu.conf'
[ "$ld_config_inventory" = "$expected_ld_config_inventory" ] || refuse
require_hash /etc/ld.so.cache \
  2cee49274627997b8652f964f3fa07912ee14ddf49566953ce4ecf057f08a5d0
require_hash /etc/ld.so.conf \
  d4b198c463418b493208485def26a6f4c57279467b9dfa491b70433cedb602e8
require_hash /etc/ld.so.conf.d/fakeroot-x86_64-linux-gnu.conf \
  af7edc777dd224bade078ba540538444db69856533c02e18a7f9fbbdd23bd181
require_hash /etc/ld.so.conf.d/ld.wsl.conf \
  cfab3f46873c9203cab45d9038643fd9b0a02d84a749d12511c5cee5e2bd77c2
require_hash /etc/ld.so.conf.d/libc.conf \
  90d4c7e43e7661cd116010eb9f50ad5817e43162df344bd1ad10898851b15d41
require_hash /etc/ld.so.conf.d/x86_64-linux-gnu.conf \
  f03e4740e6922b4f4a1181cd696b52f62f9f10d003740a8940f7121795c59c98

require_metadata /usr/local directory root
require_metadata /usr/local/lib directory root
require_absent /usr/local/lib/x86_64-linux-gnu
require_metadata /usr/lib/wsl directory root
require_metadata /usr/lib/wsl/lib directory root
require_root_tree /usr/local/lib
require_root_tree /usr/lib/wsl/lib
require_root_tree /usr/lib64
require_root_tree /usr/lib/x86_64-linux-gnu
require_root_tree /usr/lib/python3.10

stdlib_symlinks=$(
  /usr/bin/busybox find /usr/lib/python3.10 -xdev -type l -print 2>/dev/null \
    | /usr/bin/busybox sort
) || refuse
expected_stdlib_symlinks='/usr/lib/python3.10/_sysconfigdata__linux_x86_64-linux-gnu.py
/usr/lib/python3.10/config-3.10-x86_64-linux-gnu/libpython3.10.so
/usr/lib/python3.10/sitecustomize.py'
[ "$stdlib_symlinks" = "$expected_stdlib_symlinks" ] || refuse
require_symlink \
  /usr/lib/python3.10/_sysconfigdata__linux_x86_64-linux-gnu.py \
  _sysconfigdata__x86_64-linux-gnu.py
require_metadata \
  /usr/lib/python3.10/_sysconfigdata__x86_64-linux-gnu.py regular root 644
require_symlink \
  /usr/lib/python3.10/config-3.10-x86_64-linux-gnu/libpython3.10.so \
  ../../x86_64-linux-gnu/libpython3.10.so.1
require_symlink /usr/lib/x86_64-linux-gnu/libpython3.10.so.1 \
  libpython3.10.so.1.0
require_metadata /usr/lib/x86_64-linux-gnu/libpython3.10.so.1.0 regular root 644
require_symlink /usr/lib/python3.10/sitecustomize.py \
  /etc/python3.10/sitecustomize.py
require_metadata /etc/python3.10 directory root
require_metadata /etc/python3.10/sitecustomize.py regular root 644

require_absent /usr/lib/python310.zip
for path_configuration in \
  /usr/bin/python._pth \
  /usr/bin/python3.10._pth \
  /usr/bin/pyvenv.cfg \
  /usr/lib/python3.10/python._pth \
  /usr/lib/python3.10/python3.10._pth \
  /usr/lib/python3.10/pybuilddir.txt \
  /usr/lib/python3.10/pyvenv.cfg \
  /usr/pyvenv.cfg; do
  require_absent "$path_configuration"
done

# Revalidate the bound identities and installer digest immediately before the
# only dynamic exec. Path replacement fails closed; the exec target stays fd 5
# and Python receives the authenticated installer only through fd 6.
python_fd_after=$(
  /usr/bin/busybox stat -Lc '%d %i %f %u %a %h %s' \
    /proc/self/fd/5 2>/dev/null
) || refuse
installer_fd_after=$(
  /usr/bin/busybox stat -Lc '%d %i %f %u %a %h %s' \
    /proc/self/fd/6 2>/dev/null
) || refuse
[ "$python_fd_after" = "$python_fd_metadata" ] || refuse
[ "$installer_fd_after" = "$installer_fd_metadata" ] || refuse
require_hash /proc/self/fd/6 "$expected_installer_sha256"
: "RAOS_ST0505_OWNER_LOCAL_INSTALLER_FD_EXEC_BOUNDARY"
exec 4<&-
exec /usr/bin/busybox env -i \
  PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  /proc/self/fd/5 -B -I -S /proc/self/fd/6
