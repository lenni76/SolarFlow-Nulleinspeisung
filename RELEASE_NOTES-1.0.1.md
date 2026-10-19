# 1.0.1 – korrigierte Regelung, Vergleich und Statusanzeigen

Die Regelung berücksichtigt den gewünschten kleinen Netzbezug in allen Modi. Der Morgenmodus nutzt die gemessene gesamte SolarFlow-Abgabe statt des Ausgangslimits. Stellbefehle halten die aktuellen Number-Grenzen und Schrittweiten ein und gelten erst nach Rückmeldung als bestätigt. Parameteränderungen kommen ohne Reload aus; beim Stoppen werden laufende Befehle abgewartet.

Neu sind ein ausdrücklich wählbarer Vergleichsmodus, Schutz vor mehreren Reglern am selben Ausgangslimit und Statusanzeigen für steuernde Logik, Begrenzungsgrund, tatsächliche Leistung, Vergleichswerte und Befehlshistorie.

## Vor dem Update

- Erstelle ein HA-Backup. Bisherige Version 1.0.0 bleibt als eigener Release in HACS auswählbar.
- Benötigt Home Assistant Core ab 2026.10.2. Hauptreferenz ist SolarFlow2400-API 1.2.1. Zehn ausgewählte Abläufe wurden zusätzlich mit API 1.2.0 geprüft.
- Die Istleistungsquelle muss die gesamte SolarFlow-Abgabe ins Haus einschließlich Batterie enthalten (`outputHomePower`). Der zusätzliche Eingang wird bei bestehender API-Zuordnung anhand der Entitätsverwaltung erkannt; andernfalls ist er unter Neu konfigurieren auszuwählen.
- Bereits umbenannte HA-Entitäten behalten ihre Kennung. Eine Neueinrichtung ist nicht erforderlich.

## Nach dem Update

Home Assistant neu starten. Auf der Geräteseite sollte als Strategie **Korrigierte Regelung** und als Ziel-Netzbezug weiterhin dein bisheriger Wert (Standard 20 W) stehen. Prüfe Istleistung, Netzleistung, bestätigtes Ausgangslimit und Regelungsproblem.

**Vergleich – bisherige Logik steuert** ist optional und übernimmt bewusst die bekannten rechnerischen Schwächen der alten Berechnung. Die korrigierte Berechnung liefert darin nur Vergleichswerte; sie sendet keine zusätzlichen Befehle. Für den regulären Betrieb mit kleinem Netzbezug ist die korrigierte Regelung vorgesehen.

## Prüfung und Grenzen

Lokal bestanden 127 Tests unter anderem mit echtem HA Core 2026.10.2, 720 Original-Rechenreferenzen, zehn zusätzliche API-1.2.0-Kompatibilitätsabläufe, offizielle Hassfest-Validierung und Ruff. Vor Erstellung dieses Releases müssen auf GitHub erneut die HA-Tests, Kompatibilitätsprüfungen, Hassfest, HACS und statische Prüfungen erfolgreich sein.

Die Gerätekommunikation und Leistungsmesswerte sind simuliert; ein Feldtest am physischen Speicher wurde nicht durchgeführt. Kurzzeitige Einspeisung nach Laständerungen wird durch eine zeitlich abgetastete Regelung nicht sicher ausgeschlossen. Die Schreibzielsperre erfasst keine fremden Automationen oder die Zendure-App. Die bisherige feste 2.700-Wh-Annahme im Reservemodell bleibt unverändert.

## Zurückrollen

In HACS die Integration öffnen, Erneut herunterladen wählen und Version **v1.0.0** auswählen; anschließend HA neu starten. Die alten drei Quellen und bestehenden Entitätskennungen bleiben erhalten; die zusätzliche Istleistungszuordnung wird von der alten Version ignoriert. Neu hinzugekommene Entitäten werden durch den alten Code nicht mehr bereitgestellt. Ein HA-Backup enthält zusätzlich den vorherigen Konfigurations- und Registry-Zustand.

Ein identischer alter Laufzeitstand mit höherer Versionsnummer 1.0.2 wird separat vorbereitet, aber nicht als neuer Standardrelease veröffentlicht, damit er das neue Update nicht automatisch ersetzt.
