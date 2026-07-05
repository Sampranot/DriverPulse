# DriverPulse

> **Scarica e installa. Zero configurazione. Zero pubblicità. Zero tracker.**

DriverPulse trova e aggiorna i driver obsoleti del tuo PC Windows. Silenzioso, gratuito, open source. Scarica il `.exe` e via.

```
Scarica da GitHub → Doppio click → 168 dispositivi scansionati in 3 secondi → 7 obsoleti trovati
```

## Perché DriverPulse?

| Driver Booster / Snappy / 3DP | DriverPulse |
|---|---|
| 20MB+ di bloat, pubblicità, toolbar | **7MB**, pulito, niente pubblicità |
| Versione "free" limitata | **100% gratuito**, tutto sbloccato |
| Telemetria verso server sconosciuti | Telemetria **locale e anonima** |
| Chiudi gli occhi e spera | **Backup + rollback** prima di ogni modifica |

## Scarica

| Piattaforma | Link |
|---|---|
| **Windows 10/11 64bit** | [`DriverPulse.exe`](https://github.com/Sampranot/DriverPulse/releases) (singolo eseguibile) |
| **Python (tutte le versioni)** | `pip install -r requirements.txt && python main.py` |

## Come si usa

```cmd
DriverPulse.exe --scan       Trova driver obsoleti (3 secondi)
DriverPulse.exe --update     Aggiorna TUTTO automaticamente
DriverPulse.exe              Avvia interfaccia grafica
```

### Esempio reale — Scansione su un PC normale

```
DriverPulse — Scan risultati:
Dispositivo                              Driver attuale                 Stato
NVIDIA GeForce RTX 2060 SUPER            32.0.15.8180                   OUTDATED  ← 965.55 disponibile!
Intel Wireless Bluetooth                 23.40.0.2                      OUTDATED
Intel Dual Band Wireless-AC 3168         23.40.1.1                      OUTDATED
Intel Ethernet Connection I219-V         12.19.2.65                     OUTDATED
Intel 300 Series SATA AHCI               18.37.6.1011                   OUTDATED
...
Trovati: 168 dispositivi | Obsoleti: 7
```

## Cosa fa esattamente

1. **Scansiona** — interroga WMI e rileva **tutti** i dispositivi hardware (GPU, WiFi, Bluetooth, chipset, audio, storage...)
2. **Confronta** — usa un database aggiornato automaticamente da **fonti ufficiali**:
   - NVIDIA API v3 → ultima versione Game Ready
   - AMD release notes → ultimo Adrenalin
   - TechPowerUp → ultimo Intel Graphics
   - Realtek → API JSON ufficiale
3. **Analizza** — per ogni hardware sconosciuto, cerca online via **DeviceHunt** e **Windows Update API**
4. **Installa** (opzionale) — prima crea un **punto di ripristino**, fa **backup del driver corrente** via `pnputil`, poi installa silenziosamente, e **rollback** se qualcosa va storto

## Compatibilità

- ✅ Windows 10 (tutte le build)
- ✅ Windows 11 (tutte le build)
- ✅ 32 e 64 bit
- ✅ Funziona anche **senza admin** (solo scan). Per installare servono privilegi elevati
- ✅ GPU NVIDIA, AMD, Intel
- ✅ WiFi/Bluetooth Intel, Realtek, MediaTek, Qualcomm

## Build da sorgente

```cmd
git clone https://github.com/Sampranot/DriverPulse
cd DriverPulse
pip install -r requirements.txt
python main.py --scan
```

## Roadmap

- [x] Scansione hardware via WMI (batch query, 3 secondi)
- [x] Database driver auto-aggiornante (NVIDIA, AMD, Intel, Realtek)
- [x] Online fallback per hardware sconosciuto (DeviceHunt, Windows Update)
- [x] Interfaccia CLI (`--scan`, `--update`, `--silent`)
- [x] Installazione driver con backup e rollback
- [x] Eseguibile standalone (no Python richiesto)
- [ ] GUI completa con un click per aggiornare
- [ ] Pianificazione scansione automatica
- [ ] Notifiche tray per driver obsoleti

## Filosofia

- **Utile**. Risolve un problema reale senza creare problemi nuovi.
- **Onesto**. Niente pubblicità, niente "edizione pro", niente tracker nascosti.
- **Leggero**. Un eseguibile da 7MB che fa il suo lavoro e basta.

---

*Creato da Samuele. DriverPulse è software libero.*
