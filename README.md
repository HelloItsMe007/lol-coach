# LoL Post-Game Coach (MVP)

Automatischer Coach für League of Legends: analysiert ein einzelnes Match über die
offizielle Riot API (keine Video-/Computer-Vision-Analyse nötig) und gibt einen
priorisierten Text-Report mit konkreten Verbesserungstipps aus.

Abgedeckte Bereiche in dieser Version:
- **Laning Phase** (CS/min, Gold-/XP-Diff zum Lane-Gegner @10min/@15min)
- **Vision & Macro** (Vision Score, Wards platziert/zerstört, jeweils für die gesamte Partie)
- **Death-Analyse** (pro Tod: isoliert/Teamfight, Vision vorhanden ja/nein)
- **Ability-Timing** (`analysis/ability_usage.py`): war das Ultimate bei einem Tod
  laut Combat-Log + Data-Dragon-Cooldown wahrscheinlich schon wieder verfügbar?
- **Recall-Timing** (`analysis/recall.py`): längere Phasen mit kritischer HP weit
  von der eigenen Basis entfernt

Alle Findings sind regelbasiert (keine ML/CV) — deterministisch und einfach nachvollziehbar.
Optional erzeugt Claude (Anthropic API) darüber ein kurzes Coaching-Intro + Fazit im
Fließtext (siehe "LLM-Narrativ" unten); die Findings selbst bleiben davon unverändert
die Faktenbasis.

Es gibt zwei Oberflächen fuer dieselbe Analyse-Pipeline: eine CLI (`python -m
lol_coach`) und eine kleine Website (`lol_coach.web`, siehe unten) — **kein Login
noetig**, da Riot-Match-Verlauf oeffentlich abrufbar ist (siehe "Website" unten).
Die Website zeigt zusaetzlich eine **Match-Liste** (letzte 10 Spiele zum
Anklicken) und eine **Trend-Analyse** ueber diese Matches (Win-Rate, CS/min,
negative Findings je Kategorie ueber Zeit) - siehe "Trend-Analyse" unten.

## Setup

1. Python 3.10+ und Abhängigkeiten installieren:
   ```bash
   pip install -r requirements-dev.txt
   ```
2. Riot Developer API Key holen:
   - Auf https://developer.riotgames.com/ mit deinem Riot-Account einloggen
   - "Personal API Key" wird direkt angezeigt (gilt 24h, danach neu generieren)
   - Für dauerhaften Zugriff: "Register Product" → Personal Application beantragen (Approval durch Riot nötig)
3. `.env.example` zu `.env` kopieren und den Key eintragen:
   ```bash
   cp .env.example .env
   ```
4. Deine Riot-ID (Name#Tag, sichtbar im Client oben rechts) und deine Platform-Region
   (z.B. `euw1`, `na1`, `kr` — sichtbar in der Client-URL/Einstellungen) bereithalten.
5. Optional für das LLM-Narrativ: `ANTHROPIC_API_KEY` in `.env` eintragen (Key von
   https://console.anthropic.com/). Ohne diesen Key funktioniert der Report weiterhin
   vollständig, nur ohne Intro/Fazit-Fließtext.

## Nutzung

```bash
python -m lol_coach analyze --riot-id "DeinName#TAG" --region euw1 --match latest
```

`--match` akzeptiert `latest` (letztes gespieltes Match) oder eine konkrete Match-ID
(z.B. `EUW1_1234567890`). Rohe API-Antworten werden unter `cache/` zwischengespeichert,
damit wiederholte Läufe während der Entwicklung nicht erneut gegen die (rate-limitierte)
API laufen — bei Bedarf `cache/` löschen, um frische Daten zu holen.

## Website (lokal)

Die Website (`src/lol_coach/web/app.py`, FastAPI) ist eine duenne HTTP-Schicht
ueber dieselbe Analyse-Pipeline wie die CLI - keine neue Analyse-Logik. Ein
Formular (Riot-ID + Region) ersetzt die CLI-Flags, `report.html` ersetzt den
Text-Report. **Kein Login/Nutzerkonto noetig**: Match-Verlauf ist ueber Riots
Account-V1/Match-V5 oeffentlich abrufbar, sobald die App einen gueltigen
Riot-API-Key haelt - genau wie op.gg/u.gg das machen.

Lokal starten:

```bash
python run_web.py
```

Das Skript macht `src/` importierbar und laedt `.env` aus dem Projektverzeichnis,
unabhaengig vom Arbeitsverzeichnis - danach ist die Seite unter
http://127.0.0.1:8420 erreichbar. Alternativ direkt per uvicorn (dann muss
`PYTHONPATH` selbst auf `src/` zeigen):

```bash
PYTHONPATH=src uvicorn lol_coach.web.app:app --reload
```

**Wichtig fuer Mehrnutzer-Betrieb**: `RiotClient`-Instanzen (mit eingebautem
Rate-Limiter) werden pro Region einmal erzeugt und wiederverwendet (Modul-Level-
Dict in `web/app.py`), nicht pro Request neu - sonst greift das Rate-Limiting
nicht korrekt ueber gleichzeitige Nutzer hinweg.

**Flow**: `/` (Riot-ID + Region) → `/matches` (letzte 10 Spiele, `fetch.py::
get_recent_match_summaries` - ohne Timeline-Fetch, nur `get_match` pro Match,
guenstiger als eine volle Analyse) → entweder `/analyze?...&match=<id>` (Einzel-
Report, wie bisher) oder `/trends?...` (Trend-Analyse ueber alle gelisteten
Matches).

## Trend-Analyse

`/trends` laedt (Match + Timeline) fuer die letzten 10 Spiele, laesst dieselben
`analyze_*`-Funktionen wie `/analyze` einmal pro Match laufen (geteilte
Hilfsfunktion `_run_findings_pipeline` in `web/app.py`) und aggregiert die
Ergebnisse rein regelbasiert in `analysis/trends.py`
(`build_trend_report`) - **kein LLM-Call ueber mehrere Matches** (Kosten/Latenz-
Entscheidung, siehe unten). Gezeigt werden Win-Rate, CS/min- und Vision-Score/min-
Durchschnitt sowie negative Findings **pro Kategorie** (laning/vision/deaths/
abilities/recall) je Match und aufsummiert - bewusst nicht feiner nach genauem
Finding-Titel aufgeschluesselt, um nicht bruechig gegenueber Formulierungs-
aenderungen in den Findings zu werden.

**Performance-Hinweis**: bis zu 10 sequenzielle (Match + Timeline)-Fetches pro
Aufruf - kann beim ersten Mal ein paar Sekunden dauern (danach durch den
Datei-Cache unter `cache/` schneller). Kein Hintergrund-Job/Async in dieser
Version (bewusste Vereinfachung), keine Datenbank - jeder Aufruf berechnet den
Trend live neu.

## Deployment (Render.com)

Empfohlener Weg fuer einen echten Server, ohne eigenes Server-/Docker-Management:

1. Repo zu GitHub pushen, auf https://render.com einen "Web Service" aus dem
   Repo anlegen
2. Root Directory: `lol-coach`
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `PYTHONPATH=src uvicorn lol_coach.web.app:app --host 0.0.0.0 --port $PORT`
5. Environment Variables im Render-Dashboard setzen (nicht im Repo!):
   `RIOT_API_KEY`, `ANTHROPIC_API_KEY` (optional)
6. Render vergibt automatisch eine HTTPS-Subdomain; eigene Domain spaeter
   nachruestbar

`.env` wird in Production nicht gebraucht - `python-dotenv` findet einfach keine
Datei und `config.py` liest die Werte direkt aus den von Render gesetzten
Umgebungsvariablen. Der eigentliche Deploy (Account, ggf. Zahlungsdaten, Domain)
ist deine Entscheidung - dieser Abschnitt bereitet nur den Weg vor.

## Riot Production API Key beantragen

Der bisherige Personal Dev Key (24h gueltig, 20 req/s, 100 req/2min) reicht fuer
lokale Entwicklung/Tests, aber nicht fuer einen oeffentlichen Dauerbetrieb.
Fuer eine echte Website:

1. Auf https://developer.riotgames.com/ einloggen (bestehender Account reicht)
2. "Apps" → "Register Product"
3. Angaben: App-Name, kurze Beschreibung, Website-URL (Render-URL als Platzhalter
   moeglich, spaeter aktualisierbar), genutzte Endpunkte (ACCOUNT-V1, MATCH-V5),
   Nutzungszweck (Coaching-Tool fuer Post-Game-Analyse)
4. Freigabe dauert erfahrungsgemaess Tage bis Wochen - bis dahin laeuft die
   Website weiter mit dem Personal Dev Key (muss taeglich erneuert werden)
5. **Kein Riot Sign-On (RSO/OAuth) noetig** - das waere nur fuer Sonderfaelle
   (z.B. Schreibzugriff, Merch-Verknuepfung) relevant, nicht fuer oeffentlich
   abrufbaren Match-Verlauf

## Tests

Läuft komplett offline gegen eine handgefertigte Beispiel-Match+Timeline-JSON unter
`tests/fixtures/` — kein Riot API Key nötig:

```bash
pytest tests/ -v
```

## LLM-Narrativ

Ist `ANTHROPIC_API_KEY` gesetzt, ruft `analysis/narrative.py` Claude einmal pro Report
auf: Prompt enthält die bereits berechneten Findings als Fakten, Claude formuliert nur
ein 2-3-Satz-Intro ("So lief dein Spiel") und ein 2-3-Satz-Fazit (priorisierte nächste
Schritte) im Fließtext — erfindet keine eigenen Zahlen. Schlägt der API-Call fehl
(Netzwerk, Rate-Limit, ungültiger Key), wird das auf stderr vermerkt und der
regelbasierte Report trotzdem vollständig ausgegeben; die LLM-Schicht ist ein reiner
Zusatz, kein Single Point of Failure.

Zusätzlich bekommt Claude pro eigenem Tod die bestätigte Ability-Reihenfolge
(Q/W/E/R, eigene und gegnerische, aus `ability_usage.death_combat_summaries`) als
Fakten mitgeliefert - z.B. "eigene Reihenfolge [Q-E-Q-W], gegnerische [Q-R-E-R-W-W-Q-E]".
Claude darf das nur gehedged kommentieren (Systemprompt verbietet Tatsachenbehauptungen
dazu), da die Sequenzen nur bestätigt sichtbare Casts zeigen, keine vollständige
Cast-Historie - und **keine** Summoner-Spell-Aussagen treffen (siehe unten, harte
API-Grenze).

## Ability-Timing & Recall-Timing

**Ability-Timing** (`analysis/ability_usage.py` + `analysis/ddragon.py`): Riots
Timeline liefert keinen generischen "wann wurde welche Ability gecastet"-Stream,
aber jedes `CHAMPION_KILL`-Event enthält ein Combat-Log (`victimDamageDealt`/
`victimDamageReceived`), das bestätigte Ability-Einsätze zeigt — sowohl wenn der
Spieler selbst stirbt (seine eigenen Casts vor dem Tod) als auch wenn er
Kill/Assist bekommt. Kombiniert mit `SKILL_LEVEL_UP`-Events (aktueller Ability-Rang)
und patch-genauen Cooldowns von Data Dragon (`ddragon.leagueoflegends.com`,
automatisch anhand `gameVersion` aufgelöst und unter `cache/ddragon/` gecacht)
ergibt das: "Ultimate wurde vor diesem Tod nie eingesetzt" bzw. "war laut
sichtbaren Daten seit ~Ns wieder verfügbar". Die harte Verfügbarkeits-Heuristik
(mit Cooldown-Rechnung) bleibt bewusst auf das Ultimate (Slot 3, höchster Impact)
beschränkt. Q/W/E werden zusätzlich als reine Ability-**Sequenzen** pro Tod
extrahiert (`death_combat_summaries`, z.B. `[Q, E, Q, W]`) und ans LLM-Narrativ
weitergereicht - dort ist die taktische Einschätzung von Timing/Reihenfolge
besser aufgehoben als in per Hand kodierten Regeln für >160 Champions.

**Wichtige Grenzen**:
- Ability-Casts sind nur in Kämpfen sichtbar, die mit einem Kill enden - reines
  Farmen/Poken ohne Kill-Abschluss bleibt unsichtbar. Deshalb sind alle Aussagen
  hier bewusst gehedged ("wahrscheinlich", "laut sichtbaren Daten") und nie als
  Gewissheit formuliert.
- **Summoner Spells (Flash etc.) sind nicht abgedeckt und werden es mit dieser
  Datenquelle auch nicht sein**: Riots Timeline hat keinen Cast-Event dafür, und
  da Flash keinen Schaden verursacht, taucht es auch nicht indirekt im Combat-Log
  auf (anders als z.B. Ignite, das als `summonerdot` erscheint). Das ist eine
  harte, verifizierte API-Grenze - keine Bastel-Lösung möglich. Für
  Flash-Erkennung bräuchte es Video/Screen-Recording-Analyse (Cooldown-Icon-OCR),
  die bewusst zurückgestellt wurde, bis sich zeigt, ob die Combat-Log-Daten
  (Ultimate-Timing + Q/W/E-Sequenzen) allein schon genug Mehrwert liefern.

**Recall-Timing** (`analysis/recall.py`): nutzt `championStats.health`/`healthMax`
pro 60s-Frame (Riot liefert kein echtes RECALL-Event) plus eine grobe
Distanz-Näherung zur eigenen Fountain, um Phasen mit kritischer HP weit von der
Basis zu erkennen. `health == 0`-Frames werden übersprungen (oft ein Frame kurz
nach dem Tod, keine echte "lebt bei 0 HP"-Situation).

## Bekannte Limitierungen (bewusst, nicht versteckt)

- **CS/min-, Gold-/XP-Diff- und Vision-Score-Richtwerte** (in `analysis/laning.py` und
  `analysis/vision.py`) sind grobe, nicht patch-/elo-kalibrierte Faustregeln — kein
  Ersatz für echte Rang-/Patch-spezifische Benchmarks.
- **Lane-Gegner-Erkennung** basiert auf Riots `teamPosition`-Feld. Bei Custom Games,
  sehr alten Matches oder unüblichen Compositions kann dieses Feld leer sein — in dem
  Fall werden Lane-Diff-Findings übersprungen statt geraten.
- **Death-Analyse**: Teammate-Positionen stammen aus dem nächstgelegenen Timeline-Frame
  (Auflösung alle 60s), nicht aus dem exakten Todeszeitpunkt — bei schnellen
  Bewegungen kann das bis zu ~60s daneben liegen. Es gibt kein Respawn-Tracking, ein
  bereits toter Teammate könnte fälschlich als "in der Nähe" gezählt werden.
  "Vision vorhanden" wird nur über eigene `WARD_PLACED`-Events in Zeit-/Ortsnähe
  approximiert, nicht über echten Fog-of-War-Status oder Ward-Restlebensdauer.
- **Vision-Metriken** liegen nur als Gesamtwert für die ganze Partie vor, nicht pro
  Zeitfenster/Spielphase.
- **Ability-Timing**: nur sichtbar in Kämpfen, die mit einem Kill enden (siehe oben);
  Data-Dragon-Champion-Dateinamen müssen exakt Riots `championName` entsprechen -
  bei Sonderfällen (z.B. Namensänderungen zwischen Riot- und ddragon-Key) schlägt
  der Fetch fehl und die Analyse wird sauber übersprungen (stderr-Hinweis).
- **Recall-Timing**: Fountain-Koordinaten sind grobe, fest codierte Näherungswerte,
  keine patch-genaue Kartendaten; HP-Auflösung liegt bei 60s pro Frame.
- **Rate Limits**: ein Personal Dev Key erlaubt 20 Requests/Sekunde und 100/2 Minuten
  und läuft nach 24h ab — für mehr als gelegentliche Testläufe braucht es einen
  genehmigten Riot-Production-Key.

## Nächste Schritte (nicht in diesem MVP)

- LLM-Fazit über den Trend-Verlauf (aktuell bewusst rein regelbasiert, siehe
  "Trend-Analyse" oben)
- Persistenz/Datenbank für Trends (aktuell wird bei jedem Aufruf live neu
  berechnet, gestützt auf den Datei-Cache)
- Charts/Visualisierung für die Trend-Tabelle (aktuell reine HTML-Tabelle)
- Video-Scrubbing zu den relevanten Momenten (Ergaenzung zum Report, kein Ersatz)
- Echtzeit-Analyse während des Spiels
- Feinere Rollen-Heuristiken (z.B. Jungle-Pathing-Bewertung, Support-spezifische Metriken)
- Bezahlmodell (Stripe o.ä.), falls die Anthropic-API-Kosten bei mehr Traffic
  relevant werden
