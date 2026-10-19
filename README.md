# SolarFlow-Nulleinspeisung

Version **1.0.1**. Lokal und mit automatisierten HA-Tests geprüft; noch nicht auf einem echten Speicher erprobt. Geprüfte Grundlage: Home Assistant Core **2026.10.2** und SolarFlow2400-API **1.2.1**.

Die PID-Regelung begrenzt die SolarFlow-Abgabe anhand des gemessenen Netzflusses und der tatsächlichen SolarFlow-Abgabe ins Haus. Standardziel sind 20 W positiver Netzbezug. Mess- und Stellverzögerungen sowie andere Erzeuger können trotzdem kurzfristige oder nicht durch die SolarFlow vermeidbare Einspeisung verursachen.

## Eigenschaften

- vollständig unabhängig von SolarFlow- und Shelly-Integrationen
- Einrichtung über die Home-Assistant-Oberfläche
- bisherige PID-Standardwerte; ein gemeinsames Leistungsbudget für alle Betriebsmodi
- alle Parameter als veränderbare Entitäten
- persistenter PID-Zustand
- Sicherheitswert bei längerem Ausfall von Eingangsdaten
- Diagnose-Entitäten und Diagnosedownload
- Reconfigure-Flow zum Wechseln der vier Entitäten
- Morgenmodus berücksichtigt den eingestellten Zielbezug und die gemessene Istleistung
- gültige Grenzen und Schrittweite des Schreibziels werden vor dem Senden berücksichtigt
- Parameteränderungen ohne vollständiges Neuladen; laufende Befehle werden beim Stoppen abgewartet

## Installation

Die Integration kann über HACS aktualisiert werden. Release **v1.0.1** wird erst nach erfolgreichen GitHub-Prüfungen veröffentlicht. Vor dem Update ein HA-Backup erstellen und nach der Installation HA neu starten. Der unveränderte Release **v1.0.0** bleibt für die Versionsauswahl und ein Zurückrollen erhalten. Hinweise stehen in [Release Notes](RELEASE_NOTES-1.0.1.md).

## Benötigte Entitäten

- Netzleistung als `sensor` (+ Bezug, − Einspeisung)
- SolarFlow-Ausgangslimit als beschreibbare `number`-Entität
- Batterieladestand als `sensor` in Prozent
- tatsächliche gesamte SolarFlow-Abgabe ins Haus als `sensor` in W oder kW, einschließlich Batterieentladung

Die Istleistung ist eine zusätzliche Messquelle; die beschreibbare Ausgangslimit-Number bleibt das Schreibziel. Bei vorhandenen Konfigurationen mit drei Entitäten kann der eindeutig zugehörige `outputHomePower`-Sensor der SolarFlow-API anhand des HA-Entitätsregisters erkannt werden. Eine explizite Auswahl hat Vorrang. Fehlende oder mehrdeutige Messquellen werden nicht durch den Sollwert ersetzt.

Die Zuordnung lässt sich die Zuordnung über **Einstellungen → Geräte & Dienste → SolarFlow-Nulleinspeisung → ⋮ → Neu konfigurieren** ändern. Dafür ist kein YAML-Umbau nötig.

## Wichtiger Hinweis

Die Integration schreibt ausschließlich über `number.set_value`. Die Kommunikation mit dem SolarFlow-Gerät bleibt Aufgabe der separat installierten SolarFlow-Integration.

Die Regelung rundet weiterhin auf 20 W; eine gröbere Schrittweite des Schreibziels wird zusätzlich eingehalten. Leistungsgrenzen werden abgerundet. Die Low-SOC-Ausgabe ist jetzt eine Obergrenze und erzwingt keine Ausgabe bei fehlendem Verbrauch. Negative Ziel-Netzbezüge werden abgewiesen.

Eine erfolgreiche Rückmeldung bedeutet einen bestätigten Sollwert, keine physisch nachgemessene Leistungsabgabe. Die API-Befehlsprüfung sollte aktiv und automatische Recovery aus bleiben. Der vorhandene Schalter „Regelung“ beendet die Regelung ohne einen zusätzlichen 0-W-Befehl; ein Sicherheitswert von 0 W ist separat konfiguriert. Der Ausfallzeitwert 0 deaktiviert weiterhin den Sicherheitswert.

## Standardwerte

| Parameter | Standard |
|---|---:|
| Kp | 0,6 |
| Ki | 0,04 |
| Kd | 0,15 |
| Ziel-Netzbezug | 20 W |
| Reserve | 5 h |
| Free-SOC-Schwelle | 90 % |
| Low-SOC-Leistungsgrenze | 100 W |
| Low-SOC-Schwelle | 30 % |
| Min-SOC-Abschaltung | 5 % |
| Morgen Start | 07:30 |
| Morgen Ende | 11:00 |
| Regelintervall | 5 s |

## Umfang der Version

Enthalten sind die vier vereinbarten Korrekturbereiche: Netzbezugsziel in allen Modi, korrekter Morgenmodus mit Istleistung, Gerätegrenzen und sichere HA-Lebenszyklen. Vergleichsmodus, Schutz vor mehreren Regler-Einträgen und zusätzliche Statusentitäten sind enthalten.

Die bisherige feste Kapazitätsannahme von 2.700 Wh im Reservemodell und die Speicherung des PID-Zustands in jedem gültigen Zyklus sind in diesem begrenzten Auftrag unverändert. Für die SolarFlow 2400 Pro ohne Zusatzakku ist die Kapazitätsannahme ein separat bekannter offener Punkt.

## Regelungsstrategie und Vergleich

Unter Einstellungen → Geräte & Dienste → SolarFlow-Nulleinspeisung → Gerät findest du die Auswahl **Regelungsstrategie**. Die neuen Entitäten werden nach Installation und HA-Neustart angelegt.

- **Korrigierte Regelung** ist die Voreinstellung. Die korrigierte Berechnung steuert; die bisherige Berechnung liefert einen zusätzlichen Vergleichswert.
- **Vergleich – bisherige Logik steuert** ist ausdrücklich einzuschalten. Die Berechnung aus Version 1.0.0 steuert; die korrigierte Berechnung wird parallel ausgewertet. Auch dann gelten Eingabeprüfung, aktuelle Stellwertgrenzen, exklusive Zielzuordnung, Befehlsbestätigung und Sicherheitswert.

Der Vergleichsmodus übernimmt die bekannten rechnerischen Schwächen der bisherigen Logik, einschließlich alter Totzone, 750-W-Puffer und Morgenberechnung anhand des Limits. Die korrigierten Einspeisebegrenzungen sind darin nicht die steuernde Berechnung. Für den regulären Betrieb mit gewünschtem kleinem Netzbezug ist die korrigierte Regelung vorgesehen. Der Ziel-Netzbezug bleibt standardmäßig 20 W.

Beide Rechnungen verwenden dieselben tatsächlich beobachteten Eingänge und den bestätigten aktuellen Stellwert, führen aber getrennte gespeicherte PID-Zustände. Die Vergleichsrechnung schreibt keine Befehle. Eine abweichende Regelwirkung auf künftige Messwerte wird damit nicht simuliert; dies ist kein vollständiger Vergleich zweier geschlossener Regelkreise. Umschaltungen warten auf laufende Befehle, benötigen kein Neuladen und übernehmen die gespeicherten Zustände. Der vorhandene PID-Reset setzt beide Zustände zurück. Sicherheitsbefehle sind von der Strategie unabhängig.

## Schutz vor doppelter Regelung

Ein Ausgangslimit kann im Einrichtungs- und Neuzuordnungsdialog nur einem Eintrag dieser Integration zugeordnet werden. Auch abgeschaltete oder nicht geladene vorhandene Einträge zählen als Zuordnung. Bei bereits vorhandenen doppelten Einträgen erhält der zuerst beanspruchende laufende Regler das Schreibrecht; weitere bleiben mit dem Status **Ausgangslimit durch anderen Regler belegt** gesperrt. Ein gesperrter Regler sendet auch keinen Sicherheitswert. Nach vollständigem Stoppen des Eigentümers kann ein wartender Eintrag das Schreibrecht beim nächsten Zyklus übernehmen. Ein ausgeschalteter, aber noch geladener Eigentümer behält seine Zuordnung.

Die Gerätekennung aus der HA-Entitätsverwaltung und die aktuelle Entitäts-ID sichern das Schreibziel ab. Eine Umbenennung des bereits erkannten Ausgangslimits wird berücksichtigt. Die Freigabe erfolgt erst nach Abschluss eines laufenden Befehls. Diese Sperre erfasst ausschließlich Einträge dieser Integration, keine fremden Automationen, Skripte, anderen Integrationen oder die Zendure-App.

## Zusätzliche Anzeigen in der Visualisierung

Auf der Geräteseite kannst du die folgenden Entitäten auswählen und über die Oberfläche einer Entitätenkarte hinzufügen:

| Anzeige | Bedeutung |
| --- | --- |
| Aktiv steuernde Logik | Welche Berechnung steuert; außerdem Ausgeschaltet, Sicherheitswert oder Zielkonflikt |
| Begrenzungsgrund | Ziel-Netzbezug, SOC/Reserve, Geräte-Maximalwert, Schrittweite, Sicherheitswert oder Schreibfehler |
| Berechnete Ausgangsleistung | Stellwert nach den Grenzen des tatsächlichen Number-Dienstes |
| Gemeldetes Ausgangslimit | Zuletzt im Zyklus gelesener bzw. nach dem Befehl gemeldeter Number-Wert; keine gemessene Abgabeleistung |
| Istleistung ins Haus | Gemessene gesamte SolarFlow-Abgabe einschließlich Batterie |
| Vergleichswerte und Differenz | Beide berechneten, auf den Dienst begrenzten Stellwerte; Differenz = korrigiert minus bisher |
| Letzter bestätigter Stellwert und Zeitpunkt | Nur nach erfolgreich abgeschlossenem, zurückgelesenem Befehl; ein übersprungener Befehl erzeugt keine Bestätigung |
| Letzter Schreibfehler und Zeitpunkt | Bleiben nach Erholung als Historie sichtbar; voller Text im Attribut `message` und in den Diagnosedaten |
| Bestätigte, fehlgeschlagene und unveränderte Stellwerte seit Start | Zählen Regelbefehle bzw. Zyklen; interne API-Wiederholungen zählen nicht als zusätzliche Reglerbefehle |

Bei ungültigen Eingängen werden aktuelle Vorschläge und Istleistung verworfen. Historische Bestätigungen und Fehler bleiben erkennbar. Zähler und Befehlshistorie beginnen mit jedem Laden des Reglers neu; die beiden PID-Zustände werden gespeichert. Keine der Anzeigen löst selbst Geräte-Schreibzugriffe aus. Die Anzeige des Sicherheitswerts bleibt nach seiner Bestätigung erhalten, ohne ihn bei jedem Zyklus erneut zu schreiben.

## Lokale Prüfung

Rechentests: `python -m pytest tests`. Gemeinsame Tests mit echtem HA und simulierter Gerätekommunikation: `python -m pytest tests ha_tests`. Abhängigkeiten sind in `ha_tests/requirements.txt` festgelegt. Die HA-Tests erwarten den unveränderten API-Quellstand in einem benachbarten Verzeichnis `SolarFlow2400ProAPI`; alternativ kann `SOLARFLOW_TEST_API_ROOT` auf dessen Stammverzeichnis zeigen.

Die Prüfung ist in [VALIDATION.md](VALIDATION.md) dokumentiert. GitHub Actions führt vor dem Release erneut die Prüfungen aus. Lokale installationsbezogene Protokolle werden nicht veröffentlicht.

## Lizenz

MIT
