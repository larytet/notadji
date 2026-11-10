#!/bin/bash
# Shallow-clone reference repos into ~/notadji/reference/<group>/<name>, strip .git, record SHAs.
set -u
DEST="${DEST:-$HOME/notadji/reference}"
MANIFEST="$DEST/MANIFEST.tsv"
mkdir -p "$DEST"
export GIT_TERMINAL_PROMPT=0

REPOS=(
  # group|owner/repo
  "openipc|OpenIPC/sandbox-fpv"
  "openipc|OpenIPC/research"
  "openipc|OpenIPC/devourer"
  "openipc|OpenIPC/waybeam"
  "openipc|OpenIPC/msposd"
  "openipc|OpenIPC/configurator"
  "openipc|OpenIPC/improver"
  "openipc|OpenIPC/aviateur"
  "openipc|OpenIPC/PixelPilot"
  "openipc|OpenIPC/decoder"
  "openipc|OpenIPC/docs"
  "openipc|OpenIPC/wiki"
  "openipc|OpenIPC/hardware"
  "openipc|OpenIPC/realtek-wlan"
  "openipc|OpenIPC/openhisilicon"
  "openipc|OpenIPC/steam-groundstations"
  "openipc|OpenIPC/firmware"
  "wifibroadcast|svpcom/wfb-ng"
  "wifibroadcast|befinitiv/wifibroadcast"
  "openhd|OpenHD/OpenHD"
  "openhd|OpenHD/QOpenHD"
  "rubyfpv|RubyFPV/RubyFPV"
  "esp32|RomanLut/hx-esp32-cam-fpv"
  "hdzero|hd-zero/hdzero-vtx"
  "hdzero|hd-zero/hdzero-goggle"
  "sdr-phy|jhshi/openofdm"
  "sdr-phy|open-sdr/openwifi"
  "sdr-phy|analogdevicesinc/hdl"
  "sdr-phy|analogdevicesinc/plutosdr-fw"
  "sdr-phy|gnuradio/gnuradio"
  "sdr-phy|bastibl/gr-ieee802-11"
  "sdr-phy|JiaoXianjun/BTLE"
  "sdr-phy|myriadrf/LimeSDR-Mini"
)

clone_one() {
  entry="$1"
  group="${entry%%|*}"; repo="${entry#*|}"; name="${repo#*/}"
  target="$DEST/$group/$name"
  [ -d "$target" ] && { echo "skip $repo"; return; }
  mkdir -p "$DEST/$group"
  if git clone --depth 1 --quiet "https://github.com/$repo.git" "$target" 2>"$target.err"; then
    sha=$(git -C "$target" rev-parse HEAD)
    lic=$(ls "$target" | grep -iE '^(license|copying)' | head -1)
    printf '%s\t%s\t%s\t%s\n' "$repo" "$group/$name" "$sha" "${lic:-NO_LICENSE_FILE}" >> "$MANIFEST"
    rm -rf "$target/.git" "$target.err"
    echo "ok   $repo"
  else
    echo "FAIL $repo: $(tail -1 "$target.err")"
    rm -rf "$target" "$target.err"
  fi
}
export -f clone_one
export DEST MANIFEST

printf 'repo\tpath\tcommit\tlicense_file\n' > "$MANIFEST"
printf '%s\n' "${REPOS[@]}" | xargs -P 6 -I{} bash -c 'clone_one "{}"'
du -sh "$DEST"/* 2>/dev/null
echo DONE
