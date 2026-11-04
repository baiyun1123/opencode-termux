#!/data/data/com.termux/files/usr/bin/bash
# Run inside Android Termux after installing a candidate. No TUI success inference.
set -euo pipefail
OUT="${1:-$PWD/opencode2-test-logs}"
mkdir -p "$OUT"
command -v getprop >/dev/null || { echo 'This test requires Android/Termux' >&2; exit 1; }
api=$(getprop ro.build.version.sdk)
(( api >= 29 )) || { echo 'Android API below supported minimum 29' >&2; exit 1; }
{
  printf 'Android: %s\nAPI: %s\nModel: %s\n' "$(getprop ro.build.version.release)" "$api" "$(getprop ro.product.model)"
  uname -a
} > "$OUT/device.txt"
status=0
for flag in version help; do
  if timeout 30 opencode2 "--$flag" > "$OUT/$flag.log" 2>&1; then
    printf '%s: PASS\n' "$flag" >> "$OUT/smoke-status.txt"
  else
    rc=$?; printf '%s: FAIL (exit %s)\n' "$flag" "$rc" >> "$OUT/smoke-status.txt"; status=1
  fi
done
printf 'TUI/input/PTY/background/Ctrl+B/Plan/terminal restore: NOT TESTED (manual interaction required)\n' >> "$OUT/smoke-status.txt"
printf 'Logs: %s\n' "$OUT"
exit "$status"
