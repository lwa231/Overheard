#!/usr/bin/env python3
"""Build the macOS app bundle (dist/Overheard.app) with its icon. No Mac tools needed: .icns is written directly.
Double clicking the app opens Terminal and runs scripts/run.sh (connects to the board, starts everything, opens the dashboard)."""
import io
import os
import plistlib
import shutil
import stat
import struct
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "branding"))
import logo  # noqa: E402

VERSION = "1.0.0"
ICNS = [("icp4", 16), ("icp5", 32), ("icp6", 64), ("ic07", 128), ("ic11", 32), ("ic12", 64), ("ic13", 256), ("ic08", 256), ("ic14", 512), ("ic09", 512), ("ic10", 1024)]

LAUNCHER = r'''#!/bin/bash
# Overheard launcher. Finds the project, then runs it in a Terminal window (Ctrl+C there stops it).
HERE="$(cd "$(dirname "$0")/../../.." 2>/dev/null && pwd)"
for D in "$HERE" "$(cat "$HOME/.overheard-home" 2>/dev/null)" "$HOME/Desktop/ArduinoQ/unoq-netmon"; do
  [ -n "$D" ] && [ -f "$D/scripts/run.sh" ] && PROJECT="$D" && break
done
if [ -z "$PROJECT" ]; then
  osascript -e 'display alert "Overheard can not find its folder" message "Move Overheard.app back into the unoq-netmon folder, or open it once from there." as critical'
  exit 1
fi
echo "$PROJECT" > "$HOME/.overheard-home"
osascript <<EOF
tell application "Terminal"
  activate
  do script "cd " & quoted form of "$PROJECT" & " && clear && ./scripts/run.sh"
end tell
EOF
'''


def icns(img):
    chunks = b""
    for typ, px in ICNS:
        buf = io.BytesIO()
        img.resize((px, px), Image.LANCZOS).save(buf, "PNG")
        data = buf.getvalue()
        chunks += typ.encode() + struct.pack(">I", len(data) + 8) + data
    return b"icns" + struct.pack(">I", len(chunks) + 8) + chunks


def build(out):
    app = os.path.join(out, "Overheard.app")
    shutil.rmtree(app, ignore_errors=True)
    for d in ("MacOS", "Resources"):
        os.makedirs(os.path.join(app, "Contents", d))
    icon = logo.VARIANTS["a"]()
    icon.save(os.path.join(ROOT, "branding", "icon-1024.png"))
    with open(os.path.join(app, "Contents", "Resources", "AppIcon.icns"), "wb") as f:
        f.write(icns(icon))
    plist = {"CFBundleName": "Overheard", "CFBundleDisplayName": "Overheard", "CFBundleIdentifier": "com.awl.overheard",
             "CFBundleVersion": VERSION, "CFBundleShortVersionString": VERSION, "CFBundleExecutable": "Overheard",
             "CFBundleIconFile": "AppIcon", "CFBundlePackageType": "APPL", "LSMinimumSystemVersion": "11.0",
             "NSHighResolutionCapable": True, "LSUIElement": False, "NSHumanReadableCopyright": "AWL"}
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump(plist, f)
    exe = os.path.join(app, "Contents", "MacOS", "Overheard")
    with open(exe, "w") as f:
        f.write(LAUNCHER)
    os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return app


if __name__ == "__main__":
    print("built", build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")))
