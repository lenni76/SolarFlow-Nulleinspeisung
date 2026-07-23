# SolarFlow-Nulleinspeisung

Eigenständige PID-Regelung für Home Assistant 2026.07 zur Nulleinspeisung eines Zendure SolarFlow 2400 Pro anhand einer Netzleistungsmessung, z. B. Shelly Pro 3EM.

## Eigenschaften

- vollständig unabhängig von SolarFlow- und Shelly-Integrationen
- Einrichtung über die Home-Assistant-Oberfläche
- originale Standardwerte und Prioritätslogik des bereitgestellten IP-Symcon-Skripts
- alle Parameter als veränderbare Entitäten
- persistenter PID-Zustand
- Sicherheitswert bei längerem Ausfall von Eingangsdaten
- Diagnose-Entitäten und Diagnosedownload
- Reconfigure-Flow zum Wechseln der drei Entitäten

## Installation

Kopiere `custom_components/solarflow_zero_export` nach `/config/custom_components/` und starte Home Assistant neu. Danach unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **SolarFlow-Nulleinspeisung** suchen.

## Benötigte Entitäten

- Netzleistung als `sensor` (+ Bezug, − Einspeisung)
- SolarFlow-Ausgangslimit als beschreibbare `number`-Entität
- Batterieladestand als `sensor` in Prozent

## Wichtiger Hinweis

Die Integration schreibt ausschließlich über `number.set_value`. Die Kommunikation mit dem SolarFlow-Gerät bleibt Aufgabe der separat installierten SolarFlow-Integration.

## Standardwerte

| Parameter | Standard |
|---|---:|
| Kp | 0,6 |
| Ki | 0,04 |
| Kd | 0,15 |
| Ziel-Netzbezug | 20 W |
| Reserve | 5 h |
| Free-SOC-Schwelle | 90 % |
| Low-SOC-Fixausgabe | 100 W |
| Low-SOC-Schwelle | 30 % |
| Min-SOC-Abschaltung | 5 % |
| Morgen Start | 07:30 |
| Morgen Ende | 11:00 |
| Regelintervall | 5 s |

## Lizenz

MIT
