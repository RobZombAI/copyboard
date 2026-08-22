#!/usr/bin/env python3
# CopyBoard — clipboard manager stile Windows Win+V per macOS
# ⌘V apre la finestrella dei recenti; frecce/Invio o mouse per scegliere.
import os, json, time, hashlib, threading
import objc
from Foundation import NSObject, NSMakeRect, NSData, NSDate, NSTimer, NSRunLoop, NSDefaultRunLoopMode
from AppKit import (NSApplication, NSApp, NSPasteboard, NSImage, NSColor,
                    NSFont, NSBezierPath, NSStatusBar, NSMenu, NSMenuItem,
                    NSApplicationActivationPolicyAccessory)
from AppKit import (NSPanel, NSView, NSWindowStyleMaskBorderless,
                    NSWindowStyleMaskNonactivatingPanel, NSBackingStoreBuffered,
                    NSStatusWindowLevel, NSFloatingWindowLevel)
from Quartz import *
from Quartz import CoreGraphics as CG
from AppKit import NSMouseInRect

APP_DIR = os.path.expanduser("~/.copyboard")
IMG_DIR = os.path.join(APP_DIR, "images")
DB_PATH = os.path.join(APP_DIR, "history.json")
MAX_ITEMS = 50
PANEL_W, PANEL_H, ROW_H = 420, 380, 44

os.makedirs(IMG_DIR, exist_ok=True)


def load_history():
    try:
        with open(DB_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def save_history(items):
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items[:MAX_ITEMS], f)
    os.replace(tmp, DB_PATH)


class History:
    """Lista condivisa degli elementi copiati."""
    items = load_history()

    @classmethod
    def add_text(cls, text):
        # dedup: se identico al primo, skip
        if cls.items and cls.items[0]["type"] == "text" and cls.items[0]["text"] == text:
            cls.items[0]["ts"] = time.time()
            save_history(cls.items); return False
        cls._dedupe_remove(text=text)
        cls.items.insert(0, {"type": "text", "text": text, "ts": time.time()})
        del cls.items[MAX_ITEMS:]
        save_history(cls.items)
        return True

    @classmethod
    def add_image(cls, png_path):
        if cls.items and cls.items[0]["type"] == "image" and cls.items[0]["path"] == png_path:
            cls.items[0]["ts"] = time.time()
            save_history(cls.items); return False
        cls._dedupe_remove(path=png_path)
        try:
            sz = _human_size(os.path.getsize(png_path))
        except Exception:
            sz = ""
        cls.items.insert(0, {"type": "image", "path": png_path, "ts": time.time(), "size": sz})
        del cls.items[MAX_ITEMS:]
        save_history(cls.items)
        return True

    @classmethod
    def _dedupe_remove(cls, text=None, path=None):
        out = []
        for it in cls.items:
            if text is not None and it["type"] == "text" and it["text"] == text:
                continue
            if path is not None and it["type"] == "image" and it["path"] == path:
                continue
            out.append(it)
        cls.items[:] = out


def _human_size(n):
    for u in ("B", "KB", "MB"):
        if n < 1024 or u == "MB":
            return f"{n:.0f}{u}" if u == "B" else f"{n/1.0:.0f}{u}" if False else f"{round(n)}{u}" if u=="B" else f"{n/1024:.0f}KB"
        n /= 1024.0


def read_clipboard(pb):
    """Ritorna ('text', s) | ('image', png_path) | None dal pasteboard."""
    types = pb.types() or []
    s = NSStringPboardType
    if s in types:
        txt = pb.stringForType_(s)
        if txt and len(txt.strip()) > 0:
            return ("text", str(txt))
    tiff = NSTIFFPboardType
    png_t = NSPasteboardTypePNG if hasattr(NSPasteboard, "NSPasteboardTypePNG") else None
    for t in ([png_t] if png_t else []) + [tiff]:
        if t in types:
            data = pb.dataForType_(t)
            if data is None:
                continue
            img = NSImage.alloc().initWithData_(data)
            if img is None:
                continue
            h = hashlib.md5(bytes(data)).hexdigest()[:16]
            path = os.path.join(IMG_DIR, h + ".png")
            if not os.path.exists(path):
                # converti in PNG via TIFFRepresentation
                try:
                    from AppKit import NSBitmapImageFileTypePNG
                    rep = img.TIFFRepresentation()
                    bm = NSBitmapImageRep.imageRepWithData_(rep)
                    png = bm.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
                    png.writeToFile_atomically_(path, True)
                except Exception:
                    try:
                        img.initWithContentsOfFile_  # noqa
                    except Exception:
                        pass
                    continue
            return ("image", path)
    return None


def write_clipboard(item):
    """Mette l'item selezionato nella clipboard di sistema."""
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    if item["type"] == "text":
        pb.setString_forType_(item["text"], NSStringPboardType)
    else:
        img = NSImage.alloc().initWithContentsOfFile_(item["path"])
        if img:
            pb.setData_forType_(img.TIFFRepresentation(), NSTIFFPboardType)


# ---------------------------------------------------------------- picker view
# Tema macOS nativo: vibrancy HUD, blu sistema, SF Pro
ROW_H = 36
VISIBLE_ROWS = 8
FOOTER_H = 22
PAD_Y = 6
MAX_SHOW = 30

def mac_colors():
    return {
        "accent": NSColor.controlAccentColor(),
        "text": NSColor.labelColor(),
        "dim": NSColor.secondaryLabelColor(),
        "hint": NSColor.tertiaryLabelColor(),
    }

class KeyPanel(NSPanel):
    """NSPanel borderless che puo' ricevere la tastiera."""
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return True


class PickerView(NSView):
    def initWithItems_(self, _):
        self = objc.super(PickerView, self).initWithFrame_(
            NSMakeRect(0, 0, PANEL_W, PANEL_H))
        self.items = []
        self.sel = 0
        self.thumbs = []
        self.scroll = 0
        self.h = PANEL_H
        return self

    def isFlipped(self):
        return True

    def acceptsFirstResponder(self):
        return True

    def refresh(self):
        self.items = list(History.items)[:30]
        self.sel = 0
        self.scroll = 0
        n = len(self.items)
        vis = min(n, VISIBLE_ROWS)
        h = int(PAD_Y * 2 + vis * (ROW_H + 2) - 2 + FOOTER_H)
        self.h = h
        self._rebuild_thumbs()
        if self.window():
            f = self.window().frame()
            f.origin.y += f.size.height - h
            f.size.height = h
            self.window().setFrame_display_(f, True)
        self.setNeedsDisplay_(True)

    def _visible_range(self):
        vis = min(len(self.items), VISIBLE_ROWS)
        lo = max(0, min(self.scroll, len(self.items) - vis))
        return lo, lo + vis

    def _rebuild_thumbs(self):
        """Crea/aggiorna le subview thumbnail per gli item immagine."""
        for sv in list(self.thumbs):
            sv.removeFromSuperview()
        self.thumbs = []
        lo, hi = self._visible_range()
        for i in range(lo, hi):
            it = self.items[i]
            if it["type"] != "image":
                continue
            img = NSImage.alloc().initWithContentsOfFile_(it["path"])
            if not img:
                continue
            y = PAD_Y + (i - lo) * (ROW_H + 2)
            tw = ROW_H - 12
            iv = NSImageView.alloc().initWithFrame_(NSMakeRect(38, y + 6, tw + 20, tw))
            iv.setImage_(img)
            iv.setImageScaling_(1)  # NSImageScaleProportionallyUpOrDown
            iv.setWantsLayer_(True)
            iv.layer().setCornerRadius_(4.0)
            iv.layer().setMasksToBounds_(True)
            self.addSubview_(iv)
            self.thumbs.append(iv)

    def drawRect_(self, rect):
        try:
            self._draw(rect)
        except Exception:
            import traceback
            traceback.print_exc()

    @objc.python_method
    def _draw(self, rect):
        mc = mac_colors()
        w = self.bounds().size.width
        f = NSFont.systemFontOfSize_(13)
        fs = NSFont.systemFontOfSize_(10)
        if not self.items:
            self._drawtext("Clipboard vuota", 16, 20, f, mc["dim"])
            return
        lo, hi = self._visible_range()
        for i in range(lo, hi):
            it = self.items[i]
            y = PAD_Y + (i - lo) * (ROW_H + 2)
            r = NSMakeRect(6, y - 3, w - 12, ROW_H)
            sel = (i == self.sel)
            if sel:
                mc["accent"].set()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(r, 6, 6).fill()
            icon = "\U0001F5BC" if it["type"] == "image" else "\U0001F4DD"
            tcol = NSColor.whiteColor() if sel else mc["text"]
            self._drawtext(icon, r.origin.x + 10, y + 7, f, tcol)
            if it["type"] == "image":
                label = (it.get("size") and "Immagine \u00b7 " + it["size"]) or "Immagine"
                tx = r.origin.x + 76
            else:
                first_line = it["text"].strip().split("\n")[0]
                label = first_line[:70] + ("\u2026" if len(first_line) > 70 else "")
                tx = r.origin.x + 34
            self._drawtext(label, tx, y + 7, f, tcol)
        hb = self.bounds()
        fy = hb.size.height - FOOTER_H + 7
        # indicatore scroll (solo se serve), allineato al footer
        if len(self.items) > VISIBLE_ROWS:
            fsb = NSFont.boldSystemFontOfSize_(9)
            self._drawtext("\u25b2\u25bc", w - 34, fy, fsb, mc["hint"])
        self._drawtext("\u2191\u2193 incolla \u00b7 esc chiudi", 12, fy, fs, mc["hint"])
        self._drawtext("RobZomb", w - 58, fy, fs, mc["hint"])

    @objc.python_method
    def _drawtext(self, text, x, y, font, color=None):
        from AppKit import NSAttributedString
        attrs = {NSFontAttributeName: font}
        if color is not None:
            attrs[NSForegroundColorAttributeName] = color
        attr = NSAttributedString.alloc().initWithString_attributes_(str(text), attrs)
        attr.drawAtPoint_((x, y))

    @objc.python_method
    def confirm_with_item(self, item):
        print("[CopyBoard] confermato:", (item.get("text") or item.get("path"))[:40])
        write_clipboard(item)
        try:
            History.items.remove(item)
        except ValueError:
            pass
        History.items.insert(0, item)
        save_history(History.items)
        Picker.hide()

        def _paste():
            time.sleep(0.12)
            post_synthetic_cmd_v()
            print("[CopyBoard] cmd-v inviato")
        threading.Thread(target=_paste, daemon=True).start()

    def confirm(self):
        if 0 <= self.sel < len(self.items):
            self.confirm_with_item(self.items[self.sel])

    def _ensure_visible(self):
        lo, hi = self._visible_range()
        if self.sel < lo:
            self.scroll = self.sel
        elif self.sel >= hi:
            self.scroll = self.sel - VISIBLE_ROWS + 1
        self._rebuild_thumbs()

    def keyDown_(self, ev):
        c = ev.characters()
        kc = ev.keyCode()
        if kc == 125 or c == "\x1f":           # giu'
            self.sel = min(self.sel + 1, len(self.items) - 1)
            self._ensure_visible()
        elif kc == 126 or c == "\x1e":          # su
            self.sel = max(self.sel - 1, 0)
            self._ensure_visible()
        elif kc == 36 or kc == 76:              # invio
            self.confirm(); return
        elif kc == 53:                          # esc
            Picker.hide(); return
        elif c == "v" and (ev.modifierFlags() & CGEventFlags.kCGEventFlagMaskCommand):
            self.confirm(); return              # ⌘V dentro il picker = conferma
        else:
            return
        self.setNeedsDisplay_(True)

    def mouseDown_(self, ev):
        p = self.convertPoint_fromView_(ev.locationInWindow(), None)
        idx = self.scroll + int((p.y - 3) // (ROW_H + 2))
        print("[CopyBoard] click riga:", idx)
        if 0 <= idx < len(self.items):
            # un solo click = incolla subito
            self.confirm_with_item(self.items[idx])


class Picker(NSObject):
    panel = None
    view = None

    @classmethod
    def ensure(cls):
        if cls.panel:
            return
        v = PickerView.alloc().initWithItems_(None)
        st = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        p = KeyPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL_W, PANEL_H), st, NSBackingStoreBuffered, False)
        p.setLevel_(NSStatusWindowLevel + 1)
        p.setOpaque_(False)
        p.setBackgroundColor_(NSColor.clearColor())
        p.setHasShadow_(True)
        try:
            p.setAlphaValue_(0.97)
        except Exception:
            pass
        try:
            from AppKit import (NSVisualEffectView, NSVisualEffectMaterialHUDWindow,
                                NSVisualEffectBlendingModeBehindWindow, NSVisualEffectStateActive)
            ev = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, PANEL_W, PANEL_H))
            ev.setMaterial_(NSVisualEffectMaterialHUDWindow)
            ev.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
            ev.setState_(NSVisualEffectStateActive)
            ev.setWantsLayer_(True)
            ev.layer().setCornerRadius_(12.0)
            ev.layer().setBorderWidth_(1.0)
            ev.layer().setBorderColor_(NSColor.separatorColor().CGColor())
            ev.setAutoresizingMask_(1 << 1 | 1 << 2)
            ev.addSubview_(v)
            p.setContentView_(ev)
        except Exception:
            v.setWantsLayer_(True)
            p.setContentView_(v)
        p.setInitialFirstResponder_(v)
        cls.panel, cls.view = p, v
        # click fuori dal pannello -> chiudi
        from AppKit import NSEvent, NSLeftMouseDownMask
        cls.monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSLeftMouseDownMask,
            lambda ev: cls.hide() if cls.panel and cls.panel.isVisible()
                       and not NSMouseInRect(ev.locationInWindow(), cls.panel.frame(), False) else None)

    @classmethod
    def show(cls):
        cls.ensure()
        cls.view.refresh()
        f = NSScreen.mainScreen().frame()
        x = f.origin.x + f.size.width - PANEL_W - 60
        y = f.origin.y + f.size.height * 0.28
        cls.panel.setFrameTopLeftPoint_((x, y + PANEL_H))
        cls.panel.makeKeyAndOrderFront_(None)
        cls.view.window().makeFirstResponder_(cls.view)

    @classmethod
    def hide(cls):
        if cls.panel:
            cls.panel.orderOut_(None)


suppress_until = [0.0]  # timestamp fino a cui il tap lascia passare il cmd-v sintetico


def post_synthetic_cmd_v():
    suppress_until[0] = time.time() + 0.6
    for etype in (kCGEventKeyDown, kCGEventKeyUp):
        ev = CGEventCreateKeyboardEvent(None, 9, etype == kCGEventKeyDown)
        CGEventSetFlags(ev, CGEventFlags(kCGEventFlagMaskCommand))
        CGEventPost(kCGHIDEventTap, ev)


# ------------------------------------------------------------- event tap ⌘V
KEY_V = 9
tap_ref = {}


def tap_callback(proxy, etype, event, refcon):
    try:
        if etype == kCGEventKeyDown:
            flags = CGEventGetFlags(event)
            kc = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            if int(kc) == KEY_V and (int(flags) & int(kCGEventFlagMaskCommand)):
                # il nostro cmd-v sintetico: lascialo passare per incollare
                if time.time() < suppress_until[0]:
                    return event
                # se il picker è già aperto, lascia passare (gestito dal picker)
                if Picker.panel and Picker.panel.isVisible():
                    return event
                Picker.show()
                return None  # ingoia il ⌘V originale
    except Exception:
        pass
    return event


def install_tap():
    mask = CGEventMaskBit(kCGEventKeyDown)
    tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap,
                           kCGEventTapOptionDefault, mask, tap_callback, None)
    if not tap:
        print("[CopyBoard] ⚠️  Event tap negata: concedi Accessibilità in "
              "Impostazioni › Privacy › Accessibilità e riavvia CopyBoard.")
        return False
    src = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetMain(), src, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)
    tap_ref["tap"] = tap
    return True


# ------------------------------------------------------------------ app delegate
class Delegate(NSObject):
    timer = None
    last_count = -1
    last_content = None

    def applicationDidFinishLaunching_(self, note):
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        # menu barra stato
        bar = NSStatusBar.systemStatusBar()
        item = bar.statusItemWithLength_(-1)  # variable length
        item.button().setTitle_("📋")
        menu = NSMenu.alloc().init()
        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Apri cronologia (⌘V)", "openPicker:", "")
        menu.addItem_(mi)
        mi2 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Svuota cronologia", "clearHistory:", "")
        menu.addItem_(mi2)
        menu.addItem_(NSMenuItem.separatorItem())
        mq = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Esci", "terminate:", "q")
        menu.addItem_(mq)
        item.setMenu_(menu)

        self.last_count = NSPasteboard.generalPasteboard().changeCount()
        print("[CopyBoard] tap:", install_tap())
        print("[CopyBoard] creo timer...")
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.35, self, "pollClipboard:", None, True)
        print("[CopyBoard] timer aggiunto, runloop attivo")

    def openPicker_(self, sender):
        Picker.show()

    def clearHistory_(self, sender):
        History.items[:] = []
        save_history([])
        try:
            for f in os.listdir(IMG_DIR):
                os.remove(os.path.join(IMG_DIR, f))
        except Exception:
            pass

    def pollClipboard_(self, timer):
        pb = NSPasteboard.generalPasteboard()
        if pb.changeCount() == self.last_count:
            return
        self.last_count = pb.changeCount()
        got = read_clipboard(pb)
        if not got:
            return
        kind, payload = got
        if kind == "text":
            added = History.add_text(payload)
        else:
            added = History.add_image(payload)
        # aggiorna la lista live anche se il pannello è aperto
        # (add_text/add_image ritornano False se l'elemento è identico al primo: skip)
        if added and Picker.panel and Picker.panel.isVisible():
            Picker.view.refresh()


if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    dlg = Delegate.alloc().init()
    app.setDelegate_(dlg)
    app.run()
