# Validierung des Release-Kandidaten 1.0.1

Stand: 19. Oktober 2026. Lokal geprüft, nicht am produktiven Home Assistant oder physischen Gerät installiert. Die Veröffentlichung ist durch die GitHub-Prüfungen abgesichert.

Dieser Entwurf ergänzt die vier Korrekturen aus 1.0.1.dev0 um die drei ausdrücklich beauftragten Funktionen: Vergleichsmodus, exklusive Schreibziel-Zuordnung und Statusanzeigen. Die vorherigen Nachweise bleiben lokal erhalten. Installationsbezogene Rohprotokolle werden nicht veröffentlicht.

127 Tests bestanden (37 Rechentests und 90 echte HA-Tests), einschließlich des Abgleichs von 720 Original-Referenzfällen. Zehn ausgewählte Abläufe mit API 1.2.0 ebenfalls bestanden. Hauptreferenz ist die unveränderte API 1.2.1. Zeilenabdeckung: 98,25 %. Alle 23 Hassfest-Standardvalidatoren bestanden (0 ungültige Integrationen); Ruff-Code- und Formatprüfung bestanden. Bestehende Entitäts-IDs bleiben erhalten. Reproduzierbare Tests liegen in `tests` und `ha_tests`, Abhängigkeiten in `ha_tests/requirements.txt`. Die offizielle Hassfest-Prüfung wird mit dem unveränderten Quellstand aus Core 2026.10.2 ausgeführt.

Die Tests führen beide Integrationen und HA-Dienste tatsächlich aus. Physisches Gerät, Leistungsverläufe und Regleruhr sind simuliert. Tests mit dem echten Gerät, Proxmox und HA OS wurden nicht durchgeführt. Der GitHub-Workflow führt zusätzlich den HACS-Validator sowie Hassfest aus; ein Release wird nur nach erfolgreichen Prüfungen erstellt.

Die feste Kapazitätsannahme von 2.700 Wh und die Speicherung des PID-Zustands je gültigem Zyklus sind unverändert. Die Schreibzielsperre erfasst keine fremden Automationen oder die Zendure-App. Der ausdrücklich ausgewählte Vergleichsmodus lässt die bisherige Berechnung mit ihren bekannten Schwächen steuern; die korrigierte Regelung ist die Voreinstellung. Ein Messwertvergleich ist kein simulierter zweiter geschlossener Regelkreis und keine Garantie physischer Nulleinspeisung.
