#!/usr/bin/env bash
set -euo pipefail
# User-owned, loopback-only cloud test server. No sudo, public listener or tunnel.
base="${LG_VSCODE_CLOUD_DIR:-/workspace/.tools/looking-glass-vscode}"
version=4.106.3
mkdir -p "$base"
case "${1:-start}" in
  install)
    case "$(uname -m)" in x86_64) arch=amd64;; aarch64) arch=arm64;; *) exit 1;; esac
    if [[ ! -x "$base/code-server/bin/code-server" ]]; then
      curl -fL --retry 2 "https://github.com/coder/code-server/releases/download/v$version/code-server-$version-linux-$arch.tar.gz" -o "$base/server.tar.gz"
      mkdir -p "$base/code-server"
      tar -xzf "$base/server.tar.gz" --strip-components=1 -C "$base/code-server"
      rm "$base/server.tar.gz"
    fi
    "$base/code-server/bin/code-server" --version
    ;;
  start)
    mkdir -p "$base/data" "$base/extensions"
    if [[ ! -f "$base/config.yaml" ]]; then
      umask 077
      printf 'bind-addr: 127.0.0.1:8080\nauth: password\npassword: %s\ncert: false\n' "$(node -e 'process.stdout.write(require("node:crypto").randomBytes(32).toString("hex"))')" > "$base/config.yaml"
    fi
    exec "$base/code-server/bin/code-server" --config "$base/config.yaml" --user-data-dir "$base/data" --extensions-dir "$base/extensions" --disable-telemetry --disable-update-check "${2:-$(pwd)}"
    ;;
  *) echo 'Usage: cloud-server.sh install | start [workspace]' >&2; exit 2;;
esac
