#!/usr/bin/env bash
# Bode plotter launcher (SPEC.md section 5). Idempotent; extra arguments go to the app.
set -u
cd "$(dirname "$0")"

fail() { echo "[run.sh] Step failed: $1" >&2; exit 1; }

PY=""
for c in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
        PY="$c"; break
    fi
done
[ -n "$PY" ] || fail "no Python 3.11 or newer found. Install it with your package manager (e.g. 'sudo apt install python3 python3-venv')."

if [ ! -x .venv/bin/python ]; then
    echo "[run.sh] Creating .venv ..."
    "$PY" -m venv .venv || fail "creating the virtual environment. On Debian/Ubuntu install 'python3-venv'."
fi

REQ_HASH="$(.venv/bin/python -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())")"
OLD_HASH="$(cat .venv/.req_hash 2>/dev/null || true)"
if [ "$REQ_HASH" != "$OLD_HASH" ]; then
    echo "[run.sh] Installing requirements ..."
    .venv/bin/python -m pip install --upgrade pip || fail "upgrading pip"
    .venv/bin/python -m pip install -r requirements.txt || fail "installing requirements"
    .venv/bin/python -m pip install -e . || fail "installing the app"
    echo "$REQ_HASH" > .venv/.req_hash
fi

.venv/bin/python -m bodeplot "$@" || fail "the app exited with an error"
