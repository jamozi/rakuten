#!/usr/bin/busybox sh

# Static stage zero: validate fixed local inputs, then replace the inherited
# environment before any dynamic executable is started.
set -eu
set -o pipefail

PATH=/usr/bin:/bin
LANG=C
LC_ALL=C
TZ=UTC
export PATH LANG LC_ALL TZ
unset BASH_ENV ENV CDPATH GIT_DIR GIT_WORK_TREE
unset LD_PRELOAD LD_LIBRARY_PATH PYTHONHOME PYTHONPATH PYTHONSTARTUP
unset PYTHONINSPECT PYTHONOPTIMIZE PYTHONWARNINGS PYTHONBREAKPOINT
unset PYTHONUSERBASE PYTHONSAFEPATH SSL_CERT_FILE SSL_CERT_DIR SSLKEYLOGFILE

refuse() {
  /usr/bin/busybox printf '%s\n' SELF_HOSTED_WORDPRESS_LAUNCH_REFUSED
  exit 69
}

IFS=$(/usr/bin/busybox printf ' \t\n_') || refuse
IFS=${IFS%_}
umask 0077

expected_root=/home/minami/rakuten
affiliate_request_root=$expected_root/.secrets/rakuten-owner-local/requests
ace_cresta_request=$affiliate_request_root/keyword-ace-cresta-06316.json
ace_difference_request=$affiliate_request_root/keyword-ace-difference-05721.json
proteca_maxpass4_request=$affiliate_request_root/keyword-proteca-maxpass4-01471.json

case "${1-}:$#" in
  doctor:1|install-credentials:1|create-draft:1) ;;
  affiliate-verify:7)
    [ "$2" = --ace-cresta-06316-request ] || refuse
    [ "$3" = "$ace_cresta_request" ] || refuse
    [ "$4" = --ace-difference-05721-request ] || refuse
    [ "$5" = "$ace_difference_request" ] || refuse
    [ "$6" = --proteca-maxpass4-01471-request ] || refuse
    [ "$7" = "$proteca_maxpass4_request" ] || refuse
    ;;
  *) refuse ;;
esac
requested_command=$1

approved_base=b5a6157b878ca0435ee4120d33162aba5ae51f77
python_root=/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu
python_target=$python_root/bin/python3.14
python=$expected_root/.venv/bin/python
site_packages=$expected_root/.venv/lib/python3.14/site-packages
command_path=$expected_root/scripts/self_hosted_wordpress.py
runtime_manifest=$expected_root/changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json
python_inventory=$expected_root/changes/st-1703/self-hosted-minimum-start-v1/python-runtime-code-inventory.v1.sha256
stdlib_root=$python_root/lib/python3.14
python_zip=$python_root/lib/python314.zip
pyvenv_config=$expected_root/.venv/pyvenv.cfg
dynamic_library_directory=/usr/lib/x86_64-linux-gnu
dynamic_loader=$dynamic_library_directory/ld-linux-x86-64.so.2
system_libpthread=$dynamic_library_directory/libpthread.so.0
system_libdl=$dynamic_library_directory/libdl.so.2
system_libutil=$dynamic_library_directory/libutil.so.1
system_librt=$dynamic_library_directory/librt.so.1
system_libm=$dynamic_library_directory/libm.so.6
system_libc=$dynamic_library_directory/libc.so.6
newline=$(/usr/bin/busybox printf '\n_') || refuse
newline=${newline%_}
python_newline_pth=${python_target}${newline}._pth
venv_python_pth=$expected_root/.venv/bin/python._pth
python_target_pth=${python_target}._pth
python_pybuilddir=$python_root/bin/pybuilddir.txt

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

fixed_git() {
  /usr/bin/busybox env -i \
    PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    GIT_NO_REPLACE_OBJECTS=1 GIT_OPTIONAL_LOCKS=0 \
    /usr/bin/git --no-optional-locks --literal-pathspecs \
      -c core.fsmonitor=false -c core.hooksPath=/dev/null "$@"
}

[ -f /usr/bin/git ] && [ ! -L /usr/bin/git ] && [ -x /usr/bin/git ] || refuse
git_metadata=$(
  /usr/bin/busybox stat -c '%u:%a:%h' -- /usr/bin/git 2>/dev/null
) || refuse
[ "$git_metadata" = "0:755:1" ] || refuse

repository_top=$(fixed_git rev-parse --show-toplevel 2>/dev/null) || refuse
[ "$repository_top" = "$expected_root" ] || refuse
head_commit=$(fixed_git rev-parse --verify HEAD 2>/dev/null) || refuse
[ "${#head_commit}" = 40 ] || refuse
case "$head_commit" in *[!0-9a-f]*) refuse ;; esac
fixed_git merge-base --is-ancestor "$approved_base" "$head_commit" \
  >/dev/null 2>&1 || refuse

tracked_status=$(
  fixed_git status --porcelain=v1 --untracked-files=all 2>/dev/null
) || refuse
[ -z "$tracked_status" ] || refuse
fixed_git diff --no-ext-diff --no-textconv --quiet "$head_commit" -- \
  >/dev/null 2>&1 || refuse
abnormal_index=$(
  fixed_git ls-files -v 2>/dev/null | \
    /usr/bin/busybox sed -n '/^H /!{p;q;}'
) || refuse
[ -z "$abnormal_index" ] || refuse

set -- \
  changes/st-1703/self-hosted-minimum-start-v1/python-runtime-code-inventory.v1.sha256 \
  changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json \
  scripts/self_hosted_wordpress.py \
  scripts/self_hosted_wordpress_python.sh
fixed_git ls-files --error-unmatch -- "$@" >/dev/null 2>&1 || refuse
for runtime_path in "$@"; do
  working_path=$expected_root/$runtime_path
  [ -f "$working_path" ] && [ ! -L "$working_path" ] || refuse
  working_blob=$(fixed_git hash-object --no-filters -- "$runtime_path" 2>/dev/null) \
    || refuse
  head_blob=$(fixed_git rev-parse --verify "$head_commit:$runtime_path" 2>/dev/null) \
    || refuse
  [ "$working_blob" = "$head_blob" ] || refuse
done

inventory_schema=$(
  /usr/bin/busybox sed -n '1p' "$python_inventory" 2>/dev/null
) || refuse
[ "$inventory_schema" = '# schema=SELF_HOSTED_PYTHON_RUNTIME_CODE_INVENTORY_V1' ] \
  || refuse
inventory_generator=$(
  /usr/bin/busybox sed -n '2p' "$python_inventory" 2>/dev/null
) || refuse
[ "$inventory_generator" = '# generated_by=scripts/build_st1703_self_hosted_runtime_manifest.py' ] \
  || refuse
inventory_command=$(
  /usr/bin/busybox sed -n '3p' "$python_inventory" 2>/dev/null
) || refuse
[ "$inventory_command" = '# generate_command=make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile runtime-manifest-generate' ] \
  || refuse
[ "$(/usr/bin/busybox sed -n '4p' "$python_inventory" 2>/dev/null)" = "# python_base=$python_root" ] \
  || refuse
[ "$(/usr/bin/busybox sed -n '5p' "$python_inventory" 2>/dev/null)" = "# stdlib_root=$stdlib_root" ] \
  || refuse
code_path_line=$(
  /usr/bin/busybox sed -n '6p' "$python_inventory" 2>/dev/null
) || refuse
expected_code_path_sha=${code_path_line#\# code_path_sha256=}
[ "$code_path_line" = "# code_path_sha256=$expected_code_path_sha" ] \
  || refuse
[ "${#expected_code_path_sha}" = 64 ] || refuse
case "$expected_code_path_sha" in *[!0-9a-f]*) refuse ;; esac
code_count_line=$(
  /usr/bin/busybox sed -n '7p' "$python_inventory" 2>/dev/null
) || refuse
expected_code_count=${code_count_line#\# code_file_count=}
[ "$code_count_line" = "# code_file_count=$expected_code_count" ] || refuse
case "$expected_code_count" in ''|*[!0-9]*) refuse ;; esac
code_bytes_line=$(
  /usr/bin/busybox sed -n '8p' "$python_inventory" 2>/dev/null
) || refuse
expected_code_bytes=${code_bytes_line#\# code_file_bytes=}
[ "$code_bytes_line" = "# code_file_bytes=$expected_code_bytes" ] || refuse
case "$expected_code_bytes" in ''|*[!0-9]*) refuse ;; esac
executable_line=$(
  /usr/bin/busybox sed -n '9p' "$python_inventory" 2>/dev/null
) || refuse
expected_python_sha=${executable_line#\# python_executable_sha256=}
[ "$executable_line" = "# python_executable_sha256=$expected_python_sha" ] \
  || refuse
[ "$expected_python_sha" = c2afa8cc3c59d32bac482c122633a352c3910bfed85b59efd8ef49511d46bd2b ] \
  || refuse
pyvenv_line=$(
  /usr/bin/busybox sed -n '10p' "$python_inventory" 2>/dev/null
) || refuse
expected_pyvenv_sha=${pyvenv_line#\# pyvenv_cfg_sha256=}
[ "$pyvenv_line" = "# pyvenv_cfg_sha256=$expected_pyvenv_sha" ] || refuse
[ "${#expected_pyvenv_sha}" = 64 ] || refuse
case "$expected_pyvenv_sha" in *[!0-9a-f]*) refuse ;; esac
[ "$(/usr/bin/busybox sed -n '11p' "$python_inventory" 2>/dev/null)" = '# python_zip_state=ABSENT' ] \
  || refuse
[ "$(/usr/bin/busybox sed -n '12p' "$python_inventory" 2>/dev/null)" = "# dynamic_loader_path=$dynamic_loader" ] \
  || refuse
[ "$(/usr/bin/busybox sed -n '13p' "$python_inventory" 2>/dev/null)" = '# system_runtime_file_count=7' ] \
  || refuse
system_runtime_line=$(
  /usr/bin/busybox sed -n '14p' "$python_inventory" 2>/dev/null
) || refuse
expected_system_runtime_sha=${system_runtime_line#\# system_runtime_sha256=}
[ "$system_runtime_line" = "# system_runtime_sha256=$expected_system_runtime_sha" ] \
  || refuse
[ "${#expected_system_runtime_sha}" = 64 ] || refuse
case "$expected_system_runtime_sha" in *[!0-9a-f]*) refuse ;; esac
[ "$(/usr/bin/busybox sed -n '15p' "$python_inventory" 2>/dev/null)" = '# python_rpath_policy=PINNED_LOADER_INHIBIT_RPATH' ] \
  || refuse
python_bin_count_line=$(
  /usr/bin/busybox sed -n '16p' "$python_inventory" 2>/dev/null
) || refuse
expected_python_bin_count=${python_bin_count_line#\# python_bin_entry_count=}
[ "$python_bin_count_line" = "# python_bin_entry_count=$expected_python_bin_count" ] \
  || refuse
case "$expected_python_bin_count" in ''|*[!0-9]*) refuse ;; esac
python_bin_path_line=$(
  /usr/bin/busybox sed -n '17p' "$python_inventory" 2>/dev/null
) || refuse
expected_python_bin_path_sha=${python_bin_path_line#\# python_bin_path_sha256=}
[ "$python_bin_path_line" = "# python_bin_path_sha256=$expected_python_bin_path_sha" ] \
  || refuse
[ "${#expected_python_bin_path_sha}" = 64 ] || refuse
case "$expected_python_bin_path_sha" in *[!0-9a-f]*) refuse ;; esac
venv_bin_count_line=$(
  /usr/bin/busybox sed -n '18p' "$python_inventory" 2>/dev/null
) || refuse
expected_venv_bin_count=${venv_bin_count_line#\# venv_bin_entry_count=}
[ "$venv_bin_count_line" = "# venv_bin_entry_count=$expected_venv_bin_count" ] \
  || refuse
case "$expected_venv_bin_count" in ''|*[!0-9]*) refuse ;; esac
venv_bin_path_line=$(
  /usr/bin/busybox sed -n '19p' "$python_inventory" 2>/dev/null
) || refuse
expected_venv_bin_path_sha=${venv_bin_path_line#\# venv_bin_path_sha256=}
[ "$venv_bin_path_line" = "# venv_bin_path_sha256=$expected_venv_bin_path_sha" ] \
  || refuse
[ "${#expected_venv_bin_path_sha}" = 64 ] || refuse
case "$expected_venv_bin_path_sha" in *[!0-9a-f]*) refuse ;; esac
[ "$(/usr/bin/busybox sed -n '20p' "$python_inventory" 2>/dev/null)" = '# python_startup_landmark_candidate_count=4' ] \
  || refuse
startup_path_line=$(
  /usr/bin/busybox sed -n '21p' "$python_inventory" 2>/dev/null
) || refuse
expected_startup_path_sha=${startup_path_line#\# python_startup_landmark_path_sha256=}
[ "$startup_path_line" = "# python_startup_landmark_path_sha256=$expected_startup_path_sha" ] \
  || refuse
[ "${#expected_startup_path_sha}" = 64 ] || refuse
case "$expected_startup_path_sha" in *[!0-9a-f]*) refuse ;; esac
[ "$(/usr/bin/busybox sed -n '22p' "$python_inventory" 2>/dev/null)" = '# python_startup_landmark_state=ABSENT' ] \
  || refuse
[ -z "$(/usr/bin/busybox sed -n '23p' "$python_inventory" 2>/dev/null)" ] \
  || refuse

startup_path_sum=$(
  /usr/bin/busybox printf '%s\0%s\0%s\0%s\0' \
    "$python_newline_pth" \
    "$venv_python_pth" \
    "$python_target_pth" \
    "$python_pybuilddir" | \
    /usr/bin/busybox sha256sum
) || refuse
startup_path_sha=${startup_path_sum%% *}
[ "$startup_path_sha" = "$expected_startup_path_sha" ] || refuse

startup_landmarks_absent() {
  for startup_landmark in \
    "$python_newline_pth" \
    "$venv_python_pth" \
    "$python_target_pth" \
    "$python_pybuilddir"; do
    [ ! -e "$startup_landmark" ] && [ ! -L "$startup_landmark" ] || return 1
  done
}

runtime_bin_path_sets_match() {
  current_python_bin_count=$(
    /usr/bin/busybox find "$python_root/bin" -maxdepth 1 -mindepth 1 \
      -print0 2>/dev/null | \
      /usr/bin/busybox tr '\000' '\n' | \
      /usr/bin/busybox wc -l
  ) || return 1
  [ "$current_python_bin_count" = "$expected_python_bin_count" ] || return 1
  current_python_bin_sum=$(
    /usr/bin/busybox find "$python_root/bin" -maxdepth 1 -mindepth 1 \
      -print0 2>/dev/null | \
      /usr/bin/busybox sort -z | \
      /usr/bin/busybox sha256sum
  ) || return 1
  current_python_bin_sha=${current_python_bin_sum%% *}
  [ "$current_python_bin_sha" = "$expected_python_bin_path_sha" ] || return 1
  current_venv_bin_count=$(
    /usr/bin/busybox find "$expected_root/.venv/bin" -maxdepth 1 -mindepth 1 \
      -print0 2>/dev/null | \
      /usr/bin/busybox tr '\000' '\n' | \
      /usr/bin/busybox wc -l
  ) || return 1
  [ "$current_venv_bin_count" = "$expected_venv_bin_count" ] || return 1
  current_venv_bin_sum=$(
    /usr/bin/busybox find "$expected_root/.venv/bin" -maxdepth 1 -mindepth 1 \
      -print0 2>/dev/null | \
      /usr/bin/busybox sort -z | \
      /usr/bin/busybox sha256sum
  ) || return 1
  current_venv_bin_sha=${current_venv_bin_sum%% *}
  [ "$current_venv_bin_sha" = "$expected_venv_bin_path_sha" ] || return 1
}

startup_landmarks_absent || refuse
runtime_bin_path_sets_match || refuse

for trusted_system_directory in \
  / \
  /usr \
  /usr/lib \
  "$dynamic_library_directory"; do
  [ -d "$trusted_system_directory" ] && [ ! -L "$trusted_system_directory" ] \
    || refuse
  system_directory_metadata=$(
    /usr/bin/busybox stat -c '%u:%a' -- "$trusted_system_directory" 2>/dev/null
  ) || refuse
  system_directory_owner=${system_directory_metadata%%:*}
  system_directory_mode=${system_directory_metadata#*:}
  [ "$system_directory_owner" = 0 ] || refuse
  case "$system_directory_mode" in ???) ;; *) refuse ;; esac
  system_directory_group_mode=${system_directory_mode#?}
  system_directory_group_mode=${system_directory_group_mode%?}
  system_directory_other_mode=${system_directory_mode#??}
  case "$system_directory_group_mode:$system_directory_other_mode" in
    *[2367]:*|*:*[2367]) refuse ;;
  esac
done

for trusted_system_file in \
  "$dynamic_loader" \
  "$system_libpthread" \
  "$system_libdl" \
  "$system_libutil" \
  "$system_librt" \
  "$system_libm" \
  "$system_libc"; do
  [ -f "$trusted_system_file" ] && [ ! -L "$trusted_system_file" ] || refuse
  system_file_metadata=$(
    /usr/bin/busybox stat -c '%u:%a:%h' -- "$trusted_system_file" 2>/dev/null
  ) || refuse
  system_file_owner=${system_file_metadata%%:*}
  system_file_remainder=${system_file_metadata#*:}
  system_file_mode=${system_file_remainder%%:*}
  system_file_links=${system_file_remainder#*:}
  [ "$system_file_owner" = 0 ] && [ "$system_file_links" = 1 ] || refuse
  case "$system_file_mode" in ???) ;; *) refuse ;; esac
  system_file_group_mode=${system_file_mode#?}
  system_file_group_mode=${system_file_group_mode%?}
  system_file_other_mode=${system_file_mode#??}
  case "$system_file_group_mode:$system_file_other_mode" in
    *[2367]:*|*:*[2367]) refuse ;;
  esac
done
[ -x "$dynamic_loader" ] || refuse
system_runtime_sum=$(
  /usr/bin/busybox sha256sum \
    "$dynamic_loader" \
    "$system_libpthread" \
    "$system_libdl" \
    "$system_libutil" \
    "$system_librt" \
    "$system_libm" \
    "$system_libc" 2>/dev/null | \
    /usr/bin/busybox sha256sum
) || refuse
system_runtime_sha=${system_runtime_sum%% *}
[ "$system_runtime_sha" = "$expected_system_runtime_sha" ] || refuse

inventory_row_count=0
previous_inventory_relative=
while IFS=' ' read -r inventory_digest inventory_path inventory_extra; do
  case "$inventory_digest" in
    ''|'#') continue ;;
  esac
  [ -z "$inventory_extra" ] || refuse
  [ "${#inventory_digest}" = 64 ] || refuse
  case "$inventory_digest" in *[!0-9a-f]*) refuse ;; esac
  case "$inventory_path" in
    "$stdlib_root/"*) ;;
    *) refuse ;;
  esac
  inventory_relative=${inventory_path#"$stdlib_root/"}
  case "$inventory_relative" in
    ''|/*|*//*|../*|*/../*|*/..|./*|*/./*|*/.) refuse ;;
    *[!A-Za-z0-9._/+@-]*) refuse ;;
  esac
  case "$inventory_relative" in
    site-packages/*|*/site-packages/*|__pycache__/*|*/__pycache__/*) refuse ;;
    *.py|*.pyc|*.so) ;;
    *) refuse ;;
  esac
  if [ -n "$previous_inventory_relative" ]; then
    [ "$previous_inventory_relative" \< "$inventory_relative" ] || refuse
  fi
  previous_inventory_relative=$inventory_relative
  inventory_row_count=$((inventory_row_count + 1))
done < "$python_inventory"
[ "$inventory_row_count" = "$expected_code_count" ] || refuse

inventory_code_path_sum=$(
  /usr/bin/busybox sed -n '24,$p' "$python_inventory" 2>/dev/null | \
    while IFS=' ' read -r inventory_digest inventory_path inventory_extra; do
      [ -z "$inventory_extra" ] || exit 69
      inventory_relative=${inventory_path#"$stdlib_root/"}
      /usr/bin/busybox printf './%s\0' "$inventory_relative" || exit 69
    done | \
    /usr/bin/busybox sha256sum
) || refuse
inventory_code_path_sha=${inventory_code_path_sum%% *}
[ "$inventory_code_path_sha" = "$expected_code_path_sha" ] || refuse

[ ! -e "$python_zip" ] && [ ! -L "$python_zip" ] || refuse
invalid_stdlib=$(
  /usr/bin/busybox find "$stdlib_root" -xdev \
    \( -type l -o ! -user "$effective_uid" -o -perm +022 \
       -o \( ! -type f ! -type d \) \) \
    -print -quit 2>/dev/null
) || refuse
[ -z "$invalid_stdlib" ] || refuse
invalid_stdlib_link=$(
  /usr/bin/busybox find "$stdlib_root" -xdev -type f ! -links 1 \
    -print -quit 2>/dev/null
) || refuse
[ -z "$invalid_stdlib_link" ] || refuse
current_code_path_sum=$(
  cd "$stdlib_root" &&
    /usr/bin/busybox find . -xdev \
      \( -name site-packages -o -name __pycache__ \) -type d -prune -o \
      -type f \( -name '*.py' -o -name '*.pyc' -o -name '*.so' \) \
      -print0 2>/dev/null | \
    /usr/bin/busybox sort -z | \
    /usr/bin/busybox sha256sum
) || refuse
current_code_path_sha=${current_code_path_sum%% *}
[ "$current_code_path_sha" = "$expected_code_path_sha" ] || refuse
/usr/bin/busybox sed -n '24,$p' "$python_inventory" 2>/dev/null | \
  /usr/bin/busybox sha256sum -cs - >/dev/null 2>&1 || refuse

python_hash=$(
  /usr/bin/busybox sha256sum "$python" 2>/dev/null
) || refuse
[ "$python_hash" = "$expected_python_sha  $python" ] \
  || refuse
pyvenv_hash=$(
  /usr/bin/busybox sha256sum "$pyvenv_config" 2>/dev/null
) || refuse
[ "$pyvenv_hash" = "$expected_pyvenv_sha  $pyvenv_config" ] || refuse

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
  "$python_inventory" \
  "$runtime_manifest" \
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

stage_cli_blob=$(
  fixed_git rev-parse --verify \
    "$head_commit:scripts/self_hosted_wordpress.py" 2>/dev/null
) || refuse
[ "${#stage_cli_blob}" = 40 ] || refuse
case "$stage_cli_blob" in *[!0-9a-f]*) refuse ;; esac
stage_cli_size=$(
  fixed_git cat-file -s \
    "$head_commit:scripts/self_hosted_wordpress.py" 2>/dev/null
) || refuse
case "$stage_cli_size" in ''|*[!0-9]*) refuse ;; esac
[ "$stage_cli_size" -ge 1 ] && [ "$stage_cli_size" -le 131072 ] || refuse
capture_sentinel=RAOS_SELF_HOSTED_COMMITTED_CLI_CAPTURE_END_7F41B6D9
captured_cli=$(
  fixed_git cat-file blob \
    "$head_commit:scripts/self_hosted_wordpress.py" 2>/dev/null || exit 69
  /usr/bin/busybox printf '%s' "$capture_sentinel"
) || refuse
case "$captured_cli" in *"$capture_sentinel") ;; *) refuse ;; esac
captured_cli=${captured_cli%"$capture_sentinel"}
captured_cli_size=$(
  /usr/bin/busybox printf '%s' "$captured_cli" | /usr/bin/busybox wc -c
) || refuse
[ "$captured_cli_size" = "$stage_cli_size" ] || refuse
captured_cli_blob=$(
  /usr/bin/busybox printf '%s' "$captured_cli" | fixed_git hash-object --stdin
) || refuse
[ "$captured_cli_blob" = "$stage_cli_blob" ] || refuse
captured_cli_sum=$(
  /usr/bin/busybox printf '%s' "$captured_cli" | /usr/bin/busybox sha256sum
) || refuse
captured_cli_sha=${captured_cli_sum%% *}
[ "${#captured_cli_sha}" = 64 ] || refuse
case "$captured_cli_sha" in *[!0-9a-f]*) refuse ;; esac

startup_landmarks_absent || refuse
runtime_bin_path_sets_match || refuse

case "$requested_command" in
  affiliate-verify)
    set -- \
      affiliate-verify \
      --ace-cresta-06316-request "$ace_cresta_request" \
      --ace-difference-05721-request "$ace_difference_request" \
      --proteca-maxpass4-01471-request "$proteca_maxpass4_request"
    ;;
  doctor|install-credentials|create-draft) set -- "$requested_command" ;;
  *) refuse ;;
esac

/usr/bin/busybox printf '%s' "$captured_cli" | \
  /usr/bin/busybox env -i \
    PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    "RAOS_SELF_HOSTED_STAGE_HEAD=$head_commit" \
    "RAOS_SELF_HOSTED_STAGE_CLI_BLOB=$stage_cli_blob" \
    "RAOS_SELF_HOSTED_STAGE_CLI_SHA256=$captured_cli_sha" \
    "$dynamic_loader" \
      --inhibit-cache \
      --inhibit-rpath '' \
      --glibc-hwcaps-mask '' \
      --library-path "$dynamic_library_directory" \
      --argv0 "$python" \
      "$python_target" \
      -B -I -S -X pycache_prefix=/dev/null - "$@"
