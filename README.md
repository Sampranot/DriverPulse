# DriverPulse

Mantiene i driver del PC sempre aggiornati in modo silenzioso.  
Niente popup, niente toolbar, niente pubblicità.

## Come funziona

1. **Scansione** — rileva tutti i dispositivi hardware e le versioni driver correnti via WMI
2. **Confronto** — verifica se esistono versioni più recenti nel database
3. **Download** — scarica i driver aggiornati dalle fonti ufficiali
4. **Installazione** — installa in modo silenzioso senza richiedere intervento

## Utilizzo

```
python main.py              Avvia interfaccia grafica
python main.py --scan       Scansione rapida da terminale
python main.py --update     Aggiorna tutto automaticamente
python main.py --tray       Avvia in system tray
python main.py --silent     Esecuzione silenziosa (nessuna GUI)
```

## Installazione

```bash
pip install -r requirements.txt
python main.py
```

## Database driver

Il database viene aggiornato automaticamente tramite la rete di telemetria anonima.  
Puoi anche contribuire inviando statistiche hardware anonime (abilitato di default).

## Requisiti

- Windows 10 o 11
- Python 3.8+
- Connessione internet per download driver

## Progetti correlati

- **BalancePC** — ottimizzazione automatica delle risorse di sistema

---

*DriverPulse — Solo utility. Nessuna pubblicità. Nessun bloat.*
