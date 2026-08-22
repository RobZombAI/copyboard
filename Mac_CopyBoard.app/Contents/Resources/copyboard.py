#!/usr/bin/env python3
# CopyBoard — clipboard manager stile Windows Win+V per macOS
# ⌘V apre la finestrella dei recenti; frecce/Invio o mouse per scegliere.
import os, json, time, hashlib, threading
import subprocess
import objc

AX_PROMPTED = False
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
from AppKit import (NSTableView, NSTextField, NSImageView, NSScrollView,
                    NSIndexSet, NSLineBreakByWordWrapping, NSView as _NSView)

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
# UI nativa macOS: NSTableView su vibrancy HUD, selezione accento di sistema
ROW_H_MIN = 36.0
LINE_H = 16.0
MAX_LINES = 4
VISIBLE_ROWS = 8


class KeyPanel(NSPanel):
    """NSPanel borderless che puo' ricevere la tastiera."""
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return True


class PickerTable(NSTableView):
    """NSTableView con Invio/Esc/⌘V e click-singolo=incolla."""
    def keyDown_(self, ev):
        kc = ev.keyCode()
        c = ev.characters()
        if kc == 36 or kc == 76:              # invio
            self.confirmSelected(); return
        if kc == 53:                          # esc
            Picker.hide(); return
        if c == "v" and (int(ev.modifierFlags()) & int(kCGEventFlagMaskCommand)):
            self.confirmSelected(); return
        objc.super(PickerTable, self).keyDown_(ev)

    @objc.python_method
    def confirmSelected(self):
        ds = self.dataSource()
        r = self.selectedRow()
        if ds and 0 <= r < len(ds.items):
            ds.confirm_with_item(ds.items[r])

    def mouseDown_(self, ev):
        objc.super(PickerTable, self).mouseDown_(ev)
        ds = self.dataSource()
        r = self.clickedRow()
        if ds and r is not None and r >= 0 and r < len(ds.items):
            ds.confirm_with_item(ds.items[r])


class PickerData(NSObject):
    """Datasource/delegate della tabella + logica di conferma."""

    def initWithTable_(self, tv):
        self = objc.super(PickerData, self).init()
        self.items = []
        self.tv = tv
        self.h = 380
        return self

    @objc.python_method
    def refresh(self):
        self.items = list(History.items)[:30]
        self.tv.reloadData()
        if self.items:
            self.tv.selectRowIndexes_byExtendingSelection_(
                NSIndexSet.indexSetWithIndex_(0), False)
            self.tv.scrollRowToVisible_(0)
        # adatta altezza pannello al contenuto (max 8 righe)
        total = sum(self.row_height(i) for i in range(len(self.items)))
        h = min(total + 34, 8 * 38 + 40)
        self.h = h
        win = self.tv.window()
        if win and win.isVisible():
            f = win.frame()
            f.origin.y += f.size.height - h
            f.size.height = h
            win.setFrame_display_(f, True)

    @objc.python_method
    def row_height(self, i):
        if i >= len(self.items):
            return ROW_H_MIN
        it = self.items[i]
        if it["type"] == "image":
            return ROW_H_MIN
        txt = " ".join(l for l in it["text"].strip().split("\n") if l.strip())
        import math
        lines = max(1, math.ceil(len(txt) / 52.0))
        return max(ROW_H_MIN, lines * LINE_H + 10)

    # --- NSTableView datasource ---
    def numberOfRowsInTableView_(self, tv):
        return len(self.items)

    def tableView_viewForTableColumn_row_(self, tv, col, row):
        it = self.items[row]
        mc = mac_colors()
        cell = tv.makeViewWithIdentifier_owner_("cell", self)
        if cell is None:
            cell = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, PANEL_W - 16, ROW_H_MIN))
            icon = NSImageView.alloc().initWithFrame_(NSMakeRect(6, 7, 22, 22))
            icon.setTag_(1)
            icon.setImageScaling_(1)
            icon.setWantsLayer_(True)
            icon.layer().setCornerRadius_(3.0)
            icon.layer().setMasksToBounds_(True)
            txt = NSTextField.alloc().initWithFrame_(NSMakeRect(34, 6, PANEL_W - 120, ROW_H_MIN - 10))
            txt.setTag_(2)
            txt.setBezeled_(False)
            txt.setEditable_(False)
            txt.setSelectable_(False)
            txt.setDrawsBackground_(False)
            txt.setLineBreakMode_(NSLineBreakByWordWrapping)
            txt.setAutoresizingMask_(1 << 1)  # width
            cell.addSubview_(icon)
            cell.addSubview_(txt)
            cell.setIdentifier_("cell")
        icon_v = cell.viewWithTag_(1)
        txt_v = cell.viewWithTag_(2)
        txt_v.font = NSFont.systemFontOfSize_(13)
        if it["type"] == "image":
            img = NSImage.alloc().initWithContentsOfFile_(it["path"])
            icon_v.setImage_(img if img else NSImage.imageNamed_(NSImageNameMultipleDocuments))
            icon_v.setHidden_(False)
            sz = it.get("size") or ""
            txt_v.stringValue = ("Immagine \u00b7 " + sz) if sz else "Immagine"
        else:
            icon_v.setImage_(NSImage.imageNamed_(NSImageNameMultipleDocuments))
            icon_v.setHidden_(True)
            txt_v.stringValue = " ".join(l for l in it["text"].strip().split("\n") if l.strip())
            txt_v.toolTip = txt_v.stringValue[:500]
        return cell

    def tableView_heightOfRow_(self, tv, row):
        return self.row_height(row)

    # --- conferma ---
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


class Picker(NSObject):
    panel = None
    view = None

    @classmethod
    def ensure(cls):
        if cls.panel:
            return
        st = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        p = KeyPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL_W, PANEL_H), st, NSBackingStoreBuffered, False)
        p.setLevel_(NSStatusWindowLevel + 1)
        p.setOpaque_(False)
        p.setBackgroundColor_(NSColor.clearColor())
        p.setHasShadow_(True)

        # vibrancy HUD nativa
        from AppKit import (NSVisualEffectView, NSVisualEffectMaterialHUDWindow,
                            NSVisualEffectBlendingModeBehindWindow, NSVisualEffectStateActive,
                            NSScrollView)
        ev = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, PANEL_W, PANEL_H))
        ev.setMaterial_(NSVisualEffectMaterialHUDWindow)
        ev.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        ev.setState_(NSVisualEffectStateActive)
        ev.setWantsLayer_(True)
        ev.layer().setCornerRadius_(12.0)
        ev.layer().setMasksToBounds_(True)
        ev.layer().setBorderWidth_(1.0)
        ev.layer().setBorderColor_(NSColor.separatorColor().CGColor())

        # tabella nativa dentro scroll view
        from AppKit import NSTableColumn, NSTableViewStylePlain
        tv = PickerTable.alloc().initWithFrame_(NSMakeRect(0, 0, PANEL_W, PANEL_H))
        col = NSTableColumn.alloc().initWithIdentifier_("main")
        col.setWidth_(PANEL_W - 16)
        tv.addTableColumn_(col)
        tv.outlineTableColumn_ if False else None
        tv.setHeaderView_(None)
        tv.setRowHeight_(ROW_H_MIN)
        tv.setAllowsEmptySelection_(True)
        tv.setGridStyleMask_(0)
        tv.setBackgroundColor_(NSColor.clearColor())
        tv.setSelectionHighlightStyle_(1)
        tv.setUsesAlternatingRowBackgroundColors_(False)

        sv = NSScrollView.alloc().initWithFrame_(ev.bounds())
        sv.setDocumentView_(tv)
        sv.setHasVerticalScroller_(True)
        sv.setDrawsBackground_(False)
        sv.setAutohidesScrollers_(True)
        ev.addSubview_(sv)

        data = PickerData.alloc().initWithTable_(tv)
        tv.setDataSource_(data)
        tv.setDelegate_(data)
        data.refresh()

        p.setContentView_(ev)
        cls.panel, cls.view = p, data
        # click fuori dal pannello -> chiudi
        from AppKit import NSEvent, NSEventMaskLeftMouseDown
        cls.monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskLeftMouseDown,
            lambda e: cls.hide() if cls.panel and cls.panel.isVisible() else None)

    @classmethod
    def show(cls):
        cls.ensure()
        cls.view.refresh()
        f = NSScreen.mainScreen().frame()
        x = f.origin.x + f.size.width - PANEL_W - 60
        y = f.origin.y + f.size.height * 0.28
        cls.panel.setFrameTopLeftPoint_((x, y + cls.view.h))
        cls.panel.makeKeyAndOrderFront_(None)
        cls.panel.makeFirstResponder_(cls.panel.contentView().subviews()[0].documentView())

    @classmethod
    def hide(cls):
        if cls.panel:
            cls.panel.orderOut_(None)


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
    # Se non abbiamo Accessibilità, mostra il DIALOGO NATIVO di macOS
    # (kAXTrustedCheckOptionPrompt) — l'utente clicca OK una volta e poi
    # l'app funziona standalone per sempre, senza Terminal. Il prompt
    # viene mostrato UNA sola volta (flag), i retry successivi sono silenziosi.
    global AX_PROMPTED
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        from Foundation import NSDictionary
        prompt = not AX_PROMPTED
        AX_PROMPTED = True
        opts = NSDictionary.dictionaryWithObject_forKey_(prompt, "AXTrustedCheckOptionPrompt")
        if not AXIsProcessTrustedWithOptions(opts):
            if prompt:
                print("[CopyBoard] Dialogo Accessibilità mostrato — attendi il clic...")
            # non blocco: il retry timer (ogni 4s) attiverà il tap appena concesso
            return False
    except Exception as e:
        print("[CopyBoard] check AX:", e)
    mask = CGEventMaskBit(kCGEventKeyDown)
    tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap,
                           kCGEventTapOptionDefault, mask, tap_callback, None)
    if not tap:
        print("[CopyBoard] Event tap negata — apro Impostazioni › Accessibilità")
        try:
            subprocess.Popen(["open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
        except Exception:
            pass
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
        if not tap_ref.get("tap"):
            # retry automatico: quando l'utente concede l'accessibilità,
            # il tap si attiva da solo (senza riavviare l'app)
            print("[CopyBoard] retry tap ogni 4s...")
            self.tap_retry = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                4.0, self, "retryTap:", None, True)
        print("[CopyBoard] creo timer...")
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.35, self, "pollClipboard:", None, True)
        print("[CopyBoard] timer aggiunto, runloop attivo")

    def retryTap_(self, timer):
        if tap_ref.get("tap"):
            timer.invalidate()
            print("[CopyBoard] tap attivato!")
            return
        if install_tap():
            timer.invalidate()
            print("[CopyBoard] tap attivato!")

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
