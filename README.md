# 📋 Mac_CopyBoard

**Il clipboard manager stile Win+V che mancava a macOS.**

Premi ⌘V in *qualsiasi* app e invece del solito incolla si apre una finestrella con **tutto ciò che hai copiato di recente**: testi, link, screenshot, immagini. Scegli con le frecce o col mouse → viene incollato subito dove ti trovi. Fine.

> Il problema: su Windows esiste Win+V da anni. Su macOS niente di nativo, e i tool di terze parti sono pesanti, a pagamento o richiedono permessi complicati. Mac_CopyBoard è un singolo script Python (~15KB), zero dipendenze oltre a pyobjc (già sul tuo Mac), e si auto-configura sfruttando il permesso Accessibilità che Terminal ha già — **niente wizard di permessi, mai**.

![demo](https://img.shields.io/badge/macOS-13%2B-black) ![python](https://img.shields.io/badge/python-3.9-green) ![license](https://img.shields.io/badge/license-MIT-blue)

## ✨ Funzionalità

| | |
|---|---|
| ⌘V intelligente | Apre la lista dei recenti invece di incollare l'ultimo elemento |
| 📝 Testi + 🖼 Immagini | Registra tutto ciò che copi, screenshot inclusi |
| 🎯 Incolla diretto | Click o Invio → incolla nell'app di destinazione e chiudi |
| ⌨️ Navigazione completa | Frecce ⬆⬇ + Invio, click singolo, Esc per annullare |
| 📜 Scroll | Fino a 30 elementi, la lista scorre seguendo la selezione |
| 💾 Cronologia persistente | Sopravvive ai riavvii (`~/.copyboard/history.json`) |
| 🔁 Dedup automatico | Copiare due volte lo stesso testo non crea doppioni |
| 🖼 Anteprime | Thumbnail reali delle immagini copiate, con dimensione |
| 🚪 Chiudi al click fuori | Come ogni popover che si rispetti |
| 📋 Barra menu | Icona 📋 con apri cronologia / svuota / esci |
| 🚀 Autostart | LaunchAgent incluso: parte da solo al login |

## 🚀 Installazione (30 secondi)

```bash
git clone https://github.com/RobZombAI/copyboard.git
cd copyboard
./build.sh
open Mac_CopyBoard.app
```

Fatto. Al primo avvio vedrai lampeggiare una finestra di Terminal (è il meccanismo che eredita il permesso Accessibilità — vedi [Come funziona](#-come-funziona-sotto-il-cofano)) poi tutto sparisce tranne l'icona 📋 nella barra dei menu.

### Autostart al login (consigliato)

```bash
cp com.robzomb.mac-copyboard.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.robzomb.mac-copyboard.plist
```

Per disattivarlo:
```bash
launchctl unload ~/Library/LaunchAgents/com.robzomb.mac-copyboard.plist
```

## 📖 Guida operativa

### Uso quotidiano

1. **Copia come sempre** con ⌘C (testi, link) o ⌘⇧⌃4 (screenshot) — Mac_CopyBoard registra tutto in silenzio
2. Dove vuoi incollare qualcosa di **vecchio**, premi **⌘V**
3. La finestrella mostra gli ultimi elementi (fino a 30, scorri con le frecce):
   - `testo...` — anteprima della prima riga
   - `🖼 Immagine · 245KB` — immagine con thumbnail e dimensione
4. **Scegli**:
   - ⬆⬇ per muoverti, **Invio** per incollare
   - oppure **click** sulla riga = incolla immediato
   - **Esc** o click fuori = annulla senza incollare
5. L'elemento scelto torna in cima alla cronologia ed è già in clipboard

⚠️ Nota: il ⌘V "normale" ora apre sempre la lista. Se vuoi incollare proprio l'ultimo elemento senza aprire nulla, premi ⌘V e poi Invio (è la prima riga, selezionata di default).

### Gestione cronologia

```bash
# svuota tutto
python3 -c "open('$HOME/.copyboard/history.json','w').write('[]')"

# o dall'icona 📋 nella barra menu → "Svuota cronologia"
```

Le immagini copiate restano in `~/.copyboard/images/`.

### Configurazione rapida

Modifica le costanti in cima a `copyboard.py`:

| Costante | Default | Cosa fa |
|---|---|---|
| `MAX_ITEMS` | 50 | elementi massimi in cronologia |
| `PANEL_W` | 420 | larghezza finestrella (px) |
| `VISIBLE_ROWS` | 8 | righe visibili (il resto si scrolla) |
| `MAX_SHOW` | 30 | elementi massimi nella lista |

Poi riavvia: `pkill -f copyboard.py && open Mac_CopyBoard.app`

## 🔧 Come funziona sotto il cofano

Mac_CopyBoard usa tre pezzi di tecnologia Apple, senza librerie esterne:

1. **Polling pasteboard** (`NSPasteboard.changeCount`) — rileva ogni nuova copia 3 volte/sec, salva testo o PNG su disco
2. **Event tap Quartz** (`CGEventTapCreate`) — intercetta il ⌘V globale. Qui serve il permesso **Accessibilità**: invece di chiederlo all'utente, Mac_CopyBoard viene lanciato **attraverso Terminal.app** (via `osascript do script`) che eredita il permesso che Terminal già possiede. Zero configurazione.
3. **Anti-loop sintetico** — quando Mac_CopyBoard incolla, invia un ⌘V sintetico marcato con una finestra di soppressione di 600ms, così il suo stesso event tap non lo ri-intercetta (il bug classico di questo tipo di tool)

La finestrella è un `NSPanel` non attivante (`NSWindowStyleMaskNonactivatingPanel` + override di `canBecomeKeyWindow`): prende la tastiera **senza rubare il focus** all'app sotto — per questo l'incolla atterra sempre nel posto giusto.

## ❓ Troubleshooting

| Problema | Soluzione |
|---|---|
| ⌘V non apre la finestrella | `tail ~/.copyboard.log` — se vedi `tap: False`, rilancia da `Mac_CopyBoard.app` (non direttamente da python) |
| Non incolla dopo la scelta | Verifica che l'app target supporti ⌘V standard; guarda `[CopyBoard] cmd-v inviato` nel log |
| Finestra invisibile/vuota | `pkill -f copyboard.py && open Mac_CopyBoard.app` |
| Doppie icone 📋 | Un'altra istanza è viva: `pkill -f copyboard.py` |

Log completo: `~/.copyboard.log`

## 🗂 Struttura

```
Mac_CopyBoard/
├── copyboard.py      # l'intera app (~450 righe)
├── build.sh          # genera Mac_CopyBoard.app (wrapper leggero)
├── com.robzomb.mac-copyboard.plist   # LaunchAgent autostart
└── README.md
```

## Licenza

MIT — fai quello che vuoi.

---

*Realizzato da **RobZomb*** 🖤
