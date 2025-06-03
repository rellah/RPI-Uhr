# Projektplan: Digitale Produktionsuhr mit Pausenanzeige

## Systemübersicht

- **Web-App**: Python/Flask-Backend, liefert eine einfache HTML/JS-Frontendseite.
- **Raspberry Pis**: Verbinden sich per Browser (HDMI-Display + Lautsprecher).
- **Zeitsynchronisation**: Pis nutzen den Domain Controller als NTP-Server.
- **Pausenplan**: Ein globaler Pausenplan, verwaltet über eine JSON-Konfigurationsdatei auf dem Server.
- **Funktionen**:
  - Große digitale Uhranzeige.
  - Akustisches Signal bei Pausenbeginn/-ende.
  - Visueller Fortschrittsbalken während der Pause.

---

## Architekturdiagramm

```mermaid
flowchart TD
    subgraph Central_Server
        Flask[Flask Web App]
        Config[breaks.json]
    end
    subgraph Produktion
        Pi1[Raspberry Pi 1<br/>HDMI + Lautsprecher]
        Pi2[Raspberry Pi 2<br/>HDMI + Lautsprecher]
        PiN[Raspberry Pi N<br/>HDMI + Lautsprecher]
    end
    NTP[NTP Server<br/>(Domain Controller)]

    Flask -- liefert UI --> Pi1
    Flask -- liefert UI --> Pi2
    Flask -- liefert UI --> PiN
    Pi1 -- Zeitsync --> NTP
    Pi2 -- Zeitsync --> NTP
    PiN -- Zeitsync --> NTP
    Flask -- liest --> Config
```

---

## Zentrale Komponenten

- **Flask-Backend**
  - Liefert statische Frontend-Dateien.
  - Endpoint `/config.json` für den Pausenplan.
- **Konfigurationsdatei**
  - `breaks.json` (Beispiel):
    ```json
    {
      "breaks": [
        { "start": "10:00", "end": "10:15" },
        { "start": "12:00", "end": "12:30" },
        { "start": "15:00", "end": "15:15" }
      ]
    }
    ```
- **Frontend**
  - Zeigt aktuelle Uhrzeit (Browserzeit, via NTP synchronisiert).
  - Prüft aktuelle Zeit gegen Pausenplan.
  - Spielt Ton bei Pausenbeginn/-ende.
  - Zeigt Fortschrittsbalken während der Pause.

---

## Deployment

- Flask-App auf VM oder Server hosten.
- `breaks.json` auf Server ablegen/bearbeiten für Planänderungen.
- Raspberry Pis öffnen Browser im Kiosk-Modus zur Web-App-URL.
- Pis synchronisieren Zeit mit Domain Controller NTP.

---

## Umsetzungsschritte

1. Flask-Backend aufsetzen.
2. `breaks.json` und Endpoint erstellen.
3. Frontend bauen: Uhr, Pausenlogik, Ton, Fortschrittsbalken.
4. Test auf Raspberry Pi.
5. Dokumentation für Pis (Browser Kiosk-Modus, NTP-Sync).