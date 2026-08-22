#!/usr/bin/busybox sh

# Static stage zero: validate fixed local inputs, then replace the inherited
# environment before any dynamic executable is started.
refuse() {
  /usr/bin/busybox printf '%s\n' SELF_HOSTED_WORDPRESS_LAUNCH_REFUSED
  exit 69
}

IFS=$(/usr/bin/busybox printf ' \t\n_') || refuse
IFS=${IFS%_}
umask 0077

case "${1-}:$#" in
  doctor:1|install-credentials:1|create-draft:1) ;;
  *) refuse ;;
esac

expected_root=/home/minami/rakuten
python_root=/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu
python_target=$python_root/bin/python3.14
python=$expected_root/.venv/bin/python
site_packages=$expected_root/.venv/lib/python3.14/site-packages
command_path=$expected_root/scripts/self_hosted_wordpress.py

[ "${PWD-}" = "$expected_root" ] || refuse
physical_root=$(/usr/bin/busybox readlink -f -- "$PWD") || refuse
[ "$physical_root" = "$expected_root" ] || refuse

effective_uid=$(/usr/bin/busybox id -u) || refuse
case "$effective_uid" in ''|*[!0-9]*) refuse ;; esac

busybox_hash=$(
  /usr/bin/busybox sha256sum /usr/bin/busybox 2>/dev/null
) || refuse
[ "$busybox_hash" = "b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9  /usr/bin/busybox" ] \
  || refuse

python_hash=$(
  /usr/bin/busybox sha256sum "$python" 2>/dev/null
) || refuse
[ "$python_hash" = "c2afa8cc3c59d32bac482c122633a352c3910bfed85b59efd8ef49511d46bd2b  $python" ] \
  || refuse

for trusted_directory in \
  "$expected_root" \
  "$expected_root/scripts" \
  "$expected_root/python" \
  "$expected_root/python/raos" \
  "$expected_root/.venv" \
  "$expected_root/.venv/bin" \
  "$expected_root/.venv/lib" \
  "$expected_root/.venv/lib/python3.14" \
  "$site_packages" \
  "$python_root" \
  "$python_root/bin" \
  "$python_root/lib" \
  "$python_root/lib/python3.14"; do
  [ -d "$trusted_directory" ] && [ ! -L "$trusted_directory" ] || refuse
  metadata=$(
    /usr/bin/busybox stat -c '%u:%a' -- "$trusted_directory" 2>/dev/null
  ) || refuse
  owner=${metadata%%:*}
  mode=${metadata#*:}
  [ "$owner" = 0 ] || [ "$owner" = "$effective_uid" ] || refuse
  case "$mode" in ???) ;; *) refuse ;; esac
  group_mode=${mode#?}
  group_mode=${group_mode%?}
  other_mode=${mode#??}
  case "$group_mode:$other_mode" in *[2367]:*|*:*[2367]) refuse ;; esac
done

for trusted_file in \
  "$python_target" \
  "$expected_root/.venv/pyvenv.cfg" \
  "$command_path" \
  "$expected_root/scripts/build_st1703_self_hosted_theme.py"; do
  [ -f "$trusted_file" ] && [ ! -L "$trusted_file" ] || refuse
  metadata=$(
    /usr/bin/busybox stat -c '%u:%a:%h' -- "$trusted_file" 2>/dev/null
  ) || refuse
  owner=${metadata%%:*}
  remainder=${metadata#*:}
  mode=${remainder%%:*}
  links=${remainder#*:}
  [ "$owner" = "$effective_uid" ] && [ "$links" = 1 ] || refuse
  case "$mode" in ???) ;; *) refuse ;; esac
  group_mode=${mode#?}
  group_mode=${group_mode%?}
  other_mode=${mode#??}
  case "$group_mode:$other_mode" in *[2367]:*|*:*[2367]) refuse ;; esac
done

[ -L "$python" ] || refuse
python_link=$(/usr/bin/busybox readlink -- "$python") || refuse
[ "$python_link" = "$python_target" ] || refuse

invalid_site_packages=$(
  /usr/bin/busybox find "$site_packages" -xdev \
    \( -type l -o ! -user "$effective_uid" -o -perm +022 \) \
    -print -quit 2>/dev/null
) || refuse
[ -z "$invalid_site_packages" ] || refuse

invalid_python_tree=$(
  /usr/bin/busybox find "$expected_root/python/raos" -xdev \
    \( -type l -o ! -user "$effective_uid" -o -perm +022 \) \
    -print -quit 2>/dev/null
) || refuse
[ -z "$invalid_python_tree" ] || refuse

exec /usr/bin/busybox env -i \
  PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  "$python" -B -I "$command_path" "$@"
