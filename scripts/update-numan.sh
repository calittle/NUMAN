#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

step() {
    printf '\n=== %s ===\n' "$1"
}

step "Checking the NUMAN checkout"
command -v git >/dev/null 2>&1 || {
    echo "Git is not installed or is not on PATH." >&2
    exit 1
}
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "This folder is not a Git checkout. Reinstall NUMAN from GitHub." >&2
    exit 1
}
branch="$(git branch --show-current)"
if [[ "$branch" != "main" ]]; then
    echo "NUMAN is on branch '$branch', not 'main'. Inspect it before updating." >&2
    exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
    echo "Warning: this installation has local changes. Git will preserve them and stop if the update overlaps them." >&2
fi

step "Downloading the latest NUMAN release"
if ! git pull --ff-only origin main; then
    echo "Git could not fast-forward to origin/main. No local files were forcibly replaced." >&2
    exit 1
fi

step "Refreshing NUMAN's Python packages"
python_bin=".venv/bin/python"
numan_bin=".venv/bin/numan"
if [[ ! -x "$python_bin" ]]; then
    echo "NUMAN's private Python environment is missing. Follow the setup instructions first." >&2
    exit 1
fi
"$python_bin" -m pip install --upgrade -e ".[dev,live,api,wake]"

step "Preparing wake phrases"
"$numan_bin" wake compile

step "Validating the updated installation"
"$numan_bin" config validate --live
if "$numan_bin" doctor; then
    printf '\nNUMAN is up to date and ready.\n'
else
    printf '\nThe update succeeded, but the readiness check found an item that needs attention.\n' >&2
fi
