#!/bin/bash
# Build CopyBoard.app (wrapper leggero verso la venv/pyobjc di sistema)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/Mac_CopyBoard.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/MacOS/Mac_CopyBoard" <<'EOF'
#!/bin/bash
# CopyBoard launcher — passa per Terminal.app per ereditarne il permesso Accessibilità
LOG="$HOME/.copyboard.log"
for PID in $(pgrep -f "copyboard.py" 2>/dev/null); do kill -9 "$PID" 2>/dev/null; done
osascript <<'APPLESCRIPT' >/dev/null 2>&1
tell application "Terminal"
    activate
    do script "/usr/bin/python3 -u /Users/robzomb/Mac_CopyBoard/copyboard.py >> /Users/robzomb/.copyboard.log 2>&1 & exit"
end tell
APPLESCRIPT
EOF
chmod +x "$APP/Contents/MacOS/Mac_CopyBoard"

cp "$DIR/copyboard.py" "$APP/Contents/Resources/copyboard.py"

cat > "$APP/Contents/Resources/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>Mac_CopyBoard</string>
    <key>CFBundleIdentifier</key><string>com.robzomb.mac-copyboard</string>
    <key>CFBundleName</key><string>Mac_CopyBoard</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSUIElement</key><true/>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF
echo "✅ $APP"
