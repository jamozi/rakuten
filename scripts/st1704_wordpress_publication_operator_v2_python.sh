#!/usr/bin/busybox sh

# Fixed stage zero for the bounded ST-1704 publication operator v2.
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
  /usr/bin/busybox printf '%s\n' ST1704_PUBLICATION_OPERATOR_V2_LAUNCH_REFUSED >&2
  exit 69
}

IFS=$(/usr/bin/busybox printf ' \t\n_') || refuse
IFS=${IFS%_}
umask 0077

expected_root=/home/minami/rakuten
python=$expected_root/.venv/bin/python
python_target=/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu/bin/python3.14
cli_relative=scripts/st1704_wordpress_publication_operator_v2.py

article_is_allowed() {
  case "$1" in
    st1704-portable-power-station-guide|\
    st1704-anker-solix-c300-c800-c1000-differences|\
    st1704-countertop-dishwasher-for-small-households|\
    st1704-compact-robot-vacuum-shortlist) return 0 ;;
    *) return 1 ;;
  esac
}

case "${1-}:$#" in
  --help:1|status:1|revision-status:1) ;;
  propose-article-publication:3|propose-review-draft-revision:3)
    [ "$2" = --article-id ] || refuse
    article_is_allowed "$3" || refuse
    ;;
  recover-article-publication:5|apply-article-publication:5|\
  recover-review-draft-revision:5|apply-review-draft-revision:5|\
  verify-review-draft-revision:5)
    [ "$2" = --article-id ] || refuse
    article_is_allowed "$3" || refuse
    [ "$4" = --proposal-id ] || refuse
    [ "${#5}" = 64 ] || refuse
    case "$5" in *[!0-9a-f]*) refuse ;; esac
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
  changes/st-1704/publication-operator-v2/runtime-manifest.v2.json \
  python/raos/__init__.py \
  python/raos/adapters/__init__.py \
  python/raos/adapters/self_hosted_editorial_pilot_json.py \
  python/raos/adapters/self_hosted_wordpress_operator_credentials.py \
  python/raos/adapters/self_hosted_wordpress_publication_operator_https_v2.py \
  python/raos/adapters/self_hosted_wordpress_publication_operator_journal_v2.py \
  python/raos/adapters/self_hosted_wordpress_publication_operator_json_v2.py \
  python/raos/domain/editorial/self_hosted_editorial_pilot.py \
  python/raos/domain/operations/self_hosted_wordpress_operator.py \
  python/raos/domain/operations/self_hosted_wordpress_draft_revision_operator_v2.py \
  python/raos/domain/operations/self_hosted_wordpress_publication_operator_v2.py \
  python/raos/ports/__init__.py \
  python/raos/ports/self_hosted_editorial_pilot.py \
  python/raos/ports/self_hosted_wordpress_publication_operator_v2.py \
  scripts/build_st1704_wordpress_publication_operator_v2.py \
  scripts/st1704_wordpress_publication_operator_v2.py \
  scripts/st1704_wordpress_publication_operator_v2_python.sh; do
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
    RAOS_ST1704_PUBLICATION_V2_STAGE_HEAD="$head_commit" \
    RAOS_ST1704_PUBLICATION_V2_STAGE_CLI_BLOB="$cli_blob" \
    RAOS_ST1704_PUBLICATION_V2_STAGE_CLI_SHA256="$cli_sha256" \
    "$python" -B -I -S -X pycache_prefix=/dev/null - "$@"
