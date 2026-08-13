#!/bin/bash -p

set -euo pipefail

PATH=/usr/bin:/bin
export PATH

unset BASH_ENV ENV
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONOPTIMIZE
unset PYTHONWARNINGS PYTHONBREAKPOINT PYTHONUSERBASE PYTHONSAFEPATH
unset WORDPRESSCOM_CLIENT_ID WORDPRESSCOM_CLIENT_SECRET
unset WORDPRESSCOM_ACCESS_TOKEN WORDPRESSCOM_OAUTH_ACCESS_TOKEN
unset BROWSER SSL_CERT_FILE SSL_CERT_DIR SSLKEYLOGFILE
unset LD_PRELOAD LD_LIBRARY_PATH

script_directory=$(CDPATH= cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repository_root=$(CDPATH= cd -- "$script_directory/.." && pwd -P)
expected_repository_root=/home/minami/rakuten
expected_base=/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu
venv_root=$repository_root/.venv
venv_python=$venv_root/bin/python
expected_python=$expected_base/bin/python3.14

if [[ $repository_root != "$expected_repository_root" ]]; then
  printf '%s\n' 'error: WordPress.com review-draft launcher is outside the physical RAOS repository' >&2
  exit 69
fi
if [[ ! -d $venv_root || -L $venv_root || ! -d $venv_root/bin || -L $venv_root/bin ]]; then
  printf '%s\n' 'error: managed RAOS Python environment is missing or unsafe' >&2
  exit 69
fi
if [[ ! -L $venv_python || ! -x $venv_python ]]; then
  printf '%s\n' 'error: managed RAOS Python launcher is missing or unsafe' >&2
  exit 69
fi
if [[ $(/usr/bin/readlink -f -- "$venv_python") != "$expected_python" ]]; then
  printf '%s\n' 'error: managed RAOS Python target does not match 3.14.6' >&2
  exit 69
fi
if [[ ! -f $expected_python || ! -x $expected_python ]]; then
  printf '%s\n' 'error: pinned RAOS Python executable is unavailable' >&2
  exit 69
fi
if [[ $(/usr/bin/stat -c '%u' -- "$venv_root" "$venv_root/bin" "$expected_python") != "$(/usr/bin/id -u)"$'\n'"$(/usr/bin/id -u)"$'\n'"$(/usr/bin/id -u)" ]]; then
  printf '%s\n' 'error: managed RAOS Python ownership is invalid' >&2
  exit 69
fi

if ! "$venv_python" -I - "$repository_root" "$expected_base" <<'PY'
from pathlib import Path
import sys

repository_root = Path(sys.argv[1])
expected_base = Path(sys.argv[2])
expected_cfg = (
    f"home = {expected_base / 'bin'}\n"
    "implementation = CPython\n"
    "uv = 0.12.1\n"
    "version_info = 3.14.6\n"
    "include-system-site-packages = false\n"
    "prompt = raos\n"
)
valid = (
    sys.version_info[:3] == (3, 14, 6)
    and Path(sys.prefix) == repository_root / ".venv"
    and Path(sys.base_prefix) == expected_base
    and sys.flags.isolated == 1
    and (repository_root / ".venv/pyvenv.cfg").read_text(encoding="utf-8")
    == expected_cfg
)
raise SystemExit(0 if valid else 1)
PY
then
  printf '%s\n' 'error: managed RAOS Python state does not match the reviewed toolchain' >&2
  exit 69
fi

cd -- "$repository_root"
exec "$venv_python" -I "$repository_root/scripts/wordpresscom_review_draft.py" "$@"
