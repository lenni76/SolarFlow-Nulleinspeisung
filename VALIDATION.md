# Prüfbericht – SolarFlow-Nulleinspeisung 1.0.0

## Grundlage

Implementiert gegen die am 23. Juli 2026 veröffentlichte offizielle Home-Assistant-Entwicklerdokumentation zu Config Flows, Reconfigure Flows, Config Entries, Entity-Plattformen, `ConfigEntry.runtime_data`, Event-Intervallen, Manifesten, Lokalisierung und Diagnosen.

## Durchgeführte Prüfungen

- vollständige Python-Syntaxprüfung aller Module mit `compileall`
- AST-Parsing aller Python-Dateien
- JSON-Parsing von Manifest, HACS-Metadaten, Strings und Übersetzungen
- Prüfung der Repository- und Custom-Component-Struktur
- Prüfung, dass keine direkte SolarFlow- oder Shelly-Bibliothek importiert wird
- Prüfung, dass Schreibzugriffe ausschließlich über `number.set_value` erfolgen
- Prüfung der persistenten Speicherung von Integral und letztem Fehler
- Prüfung der Serialisierbarkeit veränderbarer Zeitwerte als ISO-Zeichenketten
- Rechentests für:
  - Min-SOC-Abschaltung
  - Morgenmodus und Ziel-Netzbezug
  - Low-SOC-Fixleistung
  - PID-Totzone
  - Integral-Anti-Windup
  - Zeitfenster über Mitternacht
- Prüfung der originalen Standardwerte des IP-Symcon-Skripts
- Prüfung der Prioritätsreihenfolge des IP-Symcon-Skripts

## Ergebnis

Alle oben genannten statischen Prüfungen und Rechentests bestanden.

## Nicht in dieser Umgebung ausführbar

Ein vollständiger Lauf in einer realen Home-Assistant-2026.07-Instanz sowie Hassfest-, HACS-Action- und Home-Assistant-Core-Pytest-Läufe waren in der bereitgestellten Offline-Umgebung nicht möglich. Diese Prüfungen sollten nach dem Push über GitHub Actions beziehungsweise in einer Home-Assistant-Testinstanz ergänzt werden.
