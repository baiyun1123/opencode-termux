#!/usr/bin/env bash
# Install OS prerequisites explicitly; compiler archives are handled by bootstrap-v2.py.
set -euo pipefail
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'Ubuntu Linux x86_64 required' >&2; exit 1
fi
sudo_cmd=()
if (( EUID != 0 )); then sudo_cmd=(sudo); fi
"${sudo_cmd[@]}" apt-get update
"${sudo_cmd[@]}" apt-get install -y --no-install-recommends \
  ca-certificates curl git python3 build-essential cmake ninja-build pkg-config \
  zip unzip xz-utils binutils dpkg-dev ruby perl autoconf automake libtool \
  libxml2-dev libxslt1-dev libzstd-dev zlib1g-dev libtinfo6
# On GitHub's Ubuntu image rustup is preinstalled. Fail explicitly elsewhere;
# do not pipe a floating installer into a privileged shell.
command -v rustup >/dev/null || { echo 'Install rustup from https://rustup.rs before continuing' >&2; exit 1; }
