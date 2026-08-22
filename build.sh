#!/bin/bash
# Build Mac_CopyBoard.app — standalone, nessuna finestra Terminal
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/Mac_CopyBoard.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/MacOS/Mac_CopyBoard" <<'EOF'
#!/usr/bin/python3 -u
# Launcher Mac_CopyBoard — puro Python, nessuna shell, nessun Terminal.
import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_RES = os.path.join(_HERE, "..", "Resources")
sys.path.insert(0, _RES)

_LOG = os.path.expanduser("~/.copyboard.log")
import io
_logf = open(_LOG, "a")
sys.stdout = _logf
sys.stderr = _logf

_code = open(os.path.join(_RES, "copyboard.py"), encoding="utf-8").read()
exec(compile(_code, "copyboard.py", "exec"), {"__name__": "__main__"})
EOF
chmod +x "$APP/Contents/MacOS/Mac_CopyBoard"

cp "$DIR/copyboard.py" "$APP/Contents/Resources/copyboard.py"
cp "$DIR/icon.icns" "$APP/Contents/Resources/icon.icns"

cat > "$APP/Contents/Resources/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>Mac_CopyBoard</string>
    <key>CFBundleIdentifier</key><string>com.robzomb.mac-copyboard</string>
    <key>CFBundleName</key><string>Mac_CopyBoard</string>
    <key>CFBundleDisplayName</key><string>Mac_CopyBoard</string>
    <key>CFBundleIconFile</key><string>icon</string>
    <key>CFBundleVersion</key><string>2.1.0</string>
    <key>CFBundleShortVersionString</key><string>2.1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>LSUIElement</key><true/>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSHumanReadableCopyright</key><string>© 2026 RobZomb</string>
</dict>
</plist>
EOF
echo "✅ $APP"
