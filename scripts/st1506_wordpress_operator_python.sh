#!/usr/bin/busybox sh

# Fixed stage zero for the bounded ST-1506 WordPress operator.
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
  /usr/bin/busybox printf '%s\n' ST1506_WORDPRESS_OPERATOR_LAUNCH_REFUSED >&2
  exit 69
}

IFS=$(/usr/bin/busybox printf ' \t\n_') || refuse
IFS=${IFS%_}
umask 0077

expected_root=/home/minami/rakuten
python=$expected_root/.venv/bin/python
python_target=/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu/bin/python3.14
cli_relative=scripts/st1506_wordpress_operator.py

case "${1-}:$#" in
  --help:1|status:1|verify-yoast-checksums:1|propose-yoast-profile:1|propose-theme-update:1) ;;
  apply-yoast-profile:3|apply-theme-update:3)
    [ "$2" = --proposal-id ] || refuse
    [ "${#3}" = 64 ] || refuse
    case "$3" in *[!0-9a-f]*) refuse ;; esac
    ;;
  *) refuse ;;
esac

[ "${PWD-}" = "$expected_root" ] || refuse
[ "$(/usr/bin/busybox readlink -f -- "$PWD")" = "$expected_root" ] || refuse
effective_uid=$(/usr/bin/busybox id -u) || refuse
case "$effective_uid" in ''|*[!0-9]*) refuse ;; esac

[ "$(/usr/bin/busybox sha256sum /usr/bin/busybox 2>/dev/null)" = \
  'b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9  /usr/bin/busybox' ] || refuse
[ -f /usr/bin/git ] && [ ! -L /usr/bin/git ] && [ -x /usr/bin/git ] || refuse
[ "$(/usr/bin/busybox stat -c '%u:%a:%h' -- /usr/bin/git 2>/dev/null)" = '0:755:1' ] || refuse

fixed_git() {
  /usr/bin/busybox env -i \
    PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
    GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    GIT_NO_LAZY_FETCH=1 GIT_NO_REPLACE_OBJECTS=1 \
    GIT_OPTIONAL_LOCKS=0 GIT_TERMINAL_PROMPT=0 \
    /usr/bin/git --no-optional-locks --literal-pathspecs \
      -c core.fsmonitor=false -c core.hooksPath=/dev/null \
      -C "$expected_root" "$@"
}

[ "$(fixed_git rev-parse --show-toplevel 2>/dev/null)" = "$expected_root" ] || refuse
head_commit=$(fixed_git rev-parse --verify 'HEAD^{commit}' 2>/dev/null) || refuse
[ "${#head_commit}" = 40 ] || refuse
case "$head_commit" in *[!0-9a-f]*) refuse ;; esac

for runtime_path in \
  changes/st-1506/self-hosted-wordpress-operator-bridge-v1/runtime-manifest.v1.json \
  changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json \
  python/raos/__init__.py \
  python/raos/adapters/__init__.py \
  python/raos/adapters/self_hosted_wordpress_operator_credentials.py \
  python/raos/adapters/self_hosted_wordpress_operator_https.py \
  python/raos/domain/operations/self_hosted_wordpress_operator.py \
  python/raos/ports/__init__.py \
  python/raos/ports/self_hosted_wordpress_operator.py \
  scripts/build_st1704_self_hosted_editorial_manifest.py \
  scripts/build_st1704_self_hosted_theme.py \
  scripts/st1506_wordpress_operator.py \
  scripts/st1506_wordpress_operator_python.sh; do
  fixed_git ls-files --error-unmatch -- "$runtime_path" >/dev/null 2>&1 || refuse
  working_path=$expected_root/$runtime_path
  [ -f "$working_path" ] && [ ! -L "$working_path" ] || refuse
  metadata=$(/usr/bin/busybox stat -c '%u:%a:%h:%s' -- "$working_path" 2>/dev/null) || refuse
  case "$metadata" in "$effective_uid":644:1:*|"$effective_uid":755:1:*) ;;
    *) refuse ;;
  esac
  working_blob=$(fixed_git hash-object --no-filters -- "$runtime_path" 2>/dev/null) || refuse
  head_blob=$(fixed_git rev-parse --verify "$head_commit:$runtime_path" 2>/dev/null) || refuse
  [ "$working_blob" = "$head_blob" ] || refuse
done

[ -L "$python" ] || refuse
[ "$(/usr/bin/busybox readlink -- "$python")" = "$python_target" ] || refuse
[ -f "$python_target" ] && [ ! -L "$python_target" ] && [ -x "$python_target" ] || refuse
[ "$(/usr/bin/busybox stat -c '%u:%a:%h' -- "$python_target" 2>/dev/null)" = \
  "$effective_uid:755:1" ] || refuse
[ "$(/usr/bin/busybox sha256sum "$python_target" 2>/dev/null)" = \
  "c2afa8cc3c59d32bac482c122633a352c3910bfed85b59efd8ef49511d46bd2b  $python_target" ] || refuse

cli_blob=$(fixed_git rev-parse --verify "$head_commit:$cli_relative" 2>/dev/null) || refuse
[ "${#cli_blob}" = 40 ] || refuse
case "$cli_blob" in *[!0-9a-f]*) refuse ;; esac
cli_sum=$(/usr/bin/busybox sha256sum "$expected_root/$cli_relative" 2>/dev/null) || refuse
cli_sha256=${cli_sum%% *}
[ "${#cli_sha256}" = 64 ] || refuse
case "$cli_sha256" in *[!0-9a-f]*) refuse ;; esac
[ "$(fixed_git rev-parse --verify 'HEAD^{commit}' 2>/dev/null)" = "$head_commit" ] || refuse

fixed_git cat-file blob "$head_commit:$cli_relative" 2>/dev/null | \
  /usr/bin/busybox env -i \
    PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    RAOS_ST1506_STAGE_HEAD="$head_commit" \
    RAOS_ST1506_STAGE_CLI_BLOB="$cli_blob" \
    RAOS_ST1506_STAGE_CLI_SHA256="$cli_sha256" \
    "$python" -B -I -S -X pycache_prefix=/dev/null - "$@"
