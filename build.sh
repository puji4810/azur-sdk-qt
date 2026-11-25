#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
mkdir -p build/releases
output=$(mktemp -d build/releases/bridge.XXXXXXXX)
if command -v zig >/dev/null; then
    zig cc -target x86_64-windows-gnu -DUNICODE -O2 -municode bridge/sdk-bridge-host.c \
        -o "$output/azur-sdk-host.exe" -luser32 -lgdi32 -lws2_32 -lbcrypt
    zig cc -target x86_64-windows-gnu -O2 -shared bridge/sdk-bridge-proxy.c bridge/sdk-bridge.def \
        -o "$output/union_pcsdk.dll" -luser32
else
    winegcc -b x86_64-windows -DUNICODE -O2 -municode bridge/sdk-bridge-host.c \
        -o "$output/azur-sdk-host.exe" -luser32 -lgdi32 -lws2_32 -lbcrypt
    winegcc -b x86_64-windows -O2 -shared bridge/sdk-bridge-proxy.c \
        -Wl,-def:bridge/sdk-bridge.def -o "$output/union_pcsdk.dll" -luser32
fi
ln -s "releases/${output##*/}" "$output.link"
mv -Tf -- "$output.link" build/selected
