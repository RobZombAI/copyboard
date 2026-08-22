#!/bin/bash
# Build Mac_CopyBoard.app — standalone, nessuna finestra Terminal
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/Mac_CopyBoard.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/MacOS/Mac_CopyBoard" <<'EOF'
#!/bin/bash
# Launcher standalone: esegue copyboard.py direttamente, senza Terminal.
LOG="$HOME/.copyboard.log"
for PID in $(pgrep -f "Mac_CopyBoard/copyboard.py" 2>/dev/null); do
    [ "$PID" != "$$" ] && kill -9 "$PID" 2>/dev/null
done
exec /usr/bin/python3 -u "$(dirname "$0")/../Resources/copyboard.py" >> "$LOG" 2>&1
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
    <key>CFBundleVersion</key><string>2.0.0</string>
    <key>CFBundleShortVersionString</key><string>2.0.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>LSUIElement</key><true/>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSHumanReadableCopyright</key><string>© 2026 RobZomb</string>
</dict>
</plist>
EOF
echo "✅ $APP"
