# AG News

Automatisch aktualisierter IT-News-Ticker für Systemadministratoren und IT-Systemhäuser. Aktuell werden Quellmeldungen importiert, noch keine eigenständigen KI-Artikel erstellt.

## Direkt in Arcane einfügen

Voraussetzung: GitHub Actions hat das Container-Image `ghcr.io/alexgg05/ag-news:latest` gebaut und das GHCR-Paket ist öffentlich lesbar. Im GitHub-Repository unter Actions den Build kontrollieren; unter Packages gegebenenfalls die Sichtbarkeit auf Public stellen.

```yaml
services:
  ag-news:
    image: ghcr.io/alexgg05/ag-news:latest
    container_name: ag-news
    restart: unless-stopped
    ports:
      - "8089:8080"
    environment:
      TZ: Europe/Berlin
      DATABASE_URL: postgresql+psycopg2://agnews:agnews@db:5432/agnews
      APP_BASE_URL: "${APP_BASE_URL:?Öffentliche HTTPS-Adresse setzen}"
      SMTP_HOST: "${SMTP_HOST:?SMTP-Server setzen}"
      SMTP_PORT: "${SMTP_PORT:-587}"
      SMTP_FROM: "${SMTP_FROM:?Absenderadresse setzen}"
      SMTP_USER: "${SMTP_USER:-}"
      SMTP_PASSWORD: "${SMTP_PASSWORD:-}"
      TRANSLATE_URL: http://translate:5000
    depends_on:
      db:
        condition: service_healthy

  translate:
    image: libretranslate/libretranslate:v1.6.5
    restart: unless-stopped
    environment:
      LT_LOAD_ONLY: en,de
      LT_UPDATE_MODELS: "true"
    volumes:
      - ag_news_translation_models:/home/libretranslate/.local

  db:
    image: postgres:16-alpine
    container_name: ag-news-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: agnews
      POSTGRES_PASSWORD: agnews
      POSTGRES_DB: agnews
    volumes:
      - ag_news_db:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agnews -d agnews"]
      interval: 10s
      timeout: 5s
      retries: 10

volumes:
  ag_news_db:
  ag_news_translation_models:
```

Vor dem Start in Arcane die Stack-Umgebungsvariablen setzen (alternativ bei Docker Compose in einer lokalen `.env` neben der Compose-Datei):

```dotenv
APP_BASE_URL=https://news.deine-domain.de
SMTP_HOST=smtp.dein-mailanbieter.de
SMTP_PORT=587
SMTP_FROM=AG News <news@deine-domain.de>
SMTP_USER=news@deine-domain.de
SMTP_PASSWORD=HIER_DAS_SMTP_PASSWORT_EINTRAGEN
```

Die Werte sind Platzhalter: Domain, SMTP-Server und Absender durch deine echten Daten ersetzen. Das SMTP-Passwort ausschließlich lokal bzw. in Arcane eintragen, niemals ins Repository committen. Bei einem Mailanbieter mit SMTP-Anmeldung müssen `SMTP_USER` und `SMTP_PASSWORD` beide gesetzt sein; bei einem ausdrücklich ohne Anmeldung freigegebenen Relay dürfen beide leer bleiben.

`APP_BASE_URL` muss die von Benutzern erreichbare Website-Adresse sein, ohne abschließenden Schrägstrich. An diese Adresse führen die Bestätigungs- und Passwortlinks. Der SMTP-Server muss STARTTLS unterstützen (üblicherweise Port 587); implizites TLS auf Port 465 wird derzeit nicht unterstützt. Die Absenderadresse muss beim Mailanbieter erlaubt sein. Nach Änderungen den `ag-news`-Container neu erstellen, damit er die neuen Umgebungsvariablen übernimmt. Anschließend ein Testkonto registrieren und den empfangenen Bestätigungslink prüfen.

Ohne eigene Domain ist für einen lokalen Test auch `APP_BASE_URL=http://SERVER-IP:8089` möglich; für den öffentlichen Betrieb die HTTPS-Adresse verwenden.

Danach unter `http://SERVER-IP:8089` öffnen. Für öffentlichen Betrieb HTTPS per Nginx Proxy Manager/Cloudflare konfigurieren. **Vor produktivem Einsatz** das Beispielpasswort in beiden Umgebungsvariablen ändern (identischer neuer Wert; bei bereits initialisierter Datenbank zusätzlich das PostgreSQL-Passwort migrieren).

## Automatische Aktualisierung ohne API-Kosten

**Kein OpenAI-API-Schlüssel erforderlich.** Die Website sammelt alle 30 Minuten Meldungen aus RSS-Feeds und zeigt Quellenübersichten an. Dies ist noch **keine eigenständig recherchierende KI-Redaktion**: Für lange, selbst formulierte Artikel ohne API-Kosten wäre ein zusätzliches lokales LLM (z. B. Ollama auf ausreichend leistungsfähiger Hardware) erforderlich. Der aktuelle Code erzeugt keine solchen Artikel. Die Seite aktualisiert sich im Browser alle 5 Minuten.

Der Import läuft **beim Containerstart und danach alle 30 Minuten**. Der Dienst liest einen erweiterten Katalog von 30 RSS/Atom-Quellen aus Deutschland und internationalen Hersteller-/Securityquellen sowie CISA KEV als JSON, filtert Schlagwörter und speichert Titel, Zusammenfassung, Datum und Quelle. Die Webseite zeigt neue Meldungen sofort beim erneuten Laden; kein Git-Push oder Image-Update pro Nachricht erforderlich. Der Import garantiert nicht, dass alle Feeds erreichbar oder vollständig sind.

### Wie kommen ChatGPT-Briefings auf die Website?

Die bestehende ChatGPT-Automatisierung mit drei täglichen Briefings kann **nicht allein durch diese Compose-Datei direkt in die Website schreiben**. Dafür ist eine gesonderte, authentifizierte Schnittstelle oder eine externe Automatisierung nötig. **Noch nicht implementiert:** Annahme von ChatGPT-Beiträgen und KI-gestützte Erstellung sowie automatische Veröffentlichung eigener deutschsprachiger Artikel. Ein GitHub-Commit ist für neue Artikel nicht die geeignete Schnittstelle; wir verwenden dafür künftig eine geschützte Publishing-API.

## Betrieb und Grenzen

- Noch keine verifizierende KI-Redaktion, sondern Quellenaggregator.
- Quelltexte und Feed-Inhalte können Fehler enthalten; keine Sicherheitsmaßnahmen ungeprüft übernehmen.
- Vor öffentlicher Veröffentlichung Impressum, Datenschutzerklärung, Medienverantwortlichkeit und Lizenzbedingungen der Feeds prüfen.
- GitHub Actions baut neue Images bei Änderungen an `main`, ein bereits laufender Container wird **nicht automatisch ersetzt**. Arcane-Update bzw. kontrollierten Image-Updater dafür einrichten.
- Die Datenbank bleibt in einem persistenten Docker-Volume; sie ist nicht auf einen Host-Port veröffentlicht.

## Entwicklung

```bash
docker build -t ag-news .
docker run --rm -p 8089:8080 -e DATABASE_URL=sqlite:////tmp/news.db ag-news
```

Healthcheck: `/health`; RSS: `/rss.xml`.

## Quellenkatalog

Die Datei `sources.py` enthält 30 RSS-/Atom-Quellen, darunter CERT-Bund WID, BSI, Heise Security, Golem Security, Security-Insider, MSRC, Microsoft 365 Roadmap, Azure, Cisco, Fortinet, Sophos, Proxmox, GitHub Security, Ubuntu, Red Hat und weitere. Zusätzlich importiert `app.py` die offiziellen CISA-KEV-JSON-Daten für die letzten 14 Tage. Der Import akzeptiert jetzt alle Feed-Titel (ohne den alten engen Keywordfilter). Doppelte URLs werden nicht mehrfach gespeichert. **Nicht alle Quellen sind live geprüft; einzelne können 403/404 liefern oder Feed-Änderungen erfordern.** Fehler im Container-Log prüfen: `docker logs ag-news --tail 100`. Bei Golem und anderen Verlagen vor öffentlicher/kommerzieller Nutzung die Feed-Nutzungsbedingungen beachten; Inhalte nicht vollständig übernehmen.

Nach Änderungen am Repository wird ein neues Image gebaut; in Arcane danach Image neu pullen und den Container neu erstellen. Das ist nicht identisch mit dem automatischen Nachrichtenimport.

## Konten und Mailversand

Die Oberfläche bietet Suche sowie kombinierbare Quellen- und Themenfilter. Nachrichten (Übersicht, Artikelseiten und RSS) sind nur mit einer gültigen Anmeldung
lesbar. Ohne Sitzung führt der Aufruf zur Anmeldeseite. RSS-Programme benötigen
ebenfalls das Sitzungscookie; ein öffentlicher Feed ist nicht verfügbar. Registrierung,
Anmeldung, Passwortwiederherstellung und Healthcheck bleiben ohne Anmeldung erreichbar.
Konten müssen vor der ersten Anmeldung per E-Mail bestätigt
werden. Unter `/login`, `/register` und `/forgot` stehen die Kontofunktionen bereit.

Für den Versand per SMTP mit verpflichtendem STARTTLS konfigurieren:

- `APP_BASE_URL`: öffentliche HTTPS-Adresse, zum Beispiel `https://news.example.org`
- `SMTP_HOST`: SMTP-Server
- `SMTP_PORT`: STARTTLS-Port (Standard: `587`)
- `SMTP_FROM`: erlaubte Absenderadresse
- `SMTP_USER` und `SMTP_PASSWORD`: Zugangsdaten, falls der Server Anmeldung verlangt;
  das Passwort ausschließlich als Laufzeit-Secret bereitstellen.

Ohne Mailkonfiguration zeigt die Registrierung einen Hinweis; es werden keine
Bestätigungslinks in Logs ausgegeben. Bestätigungslinks gelten 60 Minuten,
Passwortlinks 30 Minuten. Beide können nur einmal verwendet werden. Die Bestätigung
benötigt einen zusätzlichen Klick auf der Zielseite, damit Mail-Linkscanner den Link
nicht verbrauchen. Bei einem Passwortwechsel werden alle Sitzungen widerrufen.
Sitzungen gelten sieben Tage. HTTPS in `APP_BASE_URL` aktiviert Secure-Cookies.
Die vorhandene Datenbank erhält automatisch zusätzliche Tabellen; bestehende
Meldungen bleiben erhalten. Für dauerhafte Konten die Datenbank persistent speichern.

Entwicklungsstart (Python 3.12):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
DATABASE_URL=sqlite:////tmp/ag-news.db .venv/bin/uvicorn app:app --port 8080
```

Integrationstest mit isolierter SQLite-Datenbank und simuliertem SMTP-Versand:

```bash
.venv/bin/python -m unittest discover -s tests -v
```


## Deutsch / English und Dark Mode

Über **EN / DE** im Seitenkopf wechseln Oberfläche und Meldungstexte zwischen Deutsch
und Englisch. Die Auswahl wird für ein Jahr im Browser gespeichert. Ohne Auswahl
ist Deutsch voreingestellt. Der Hell-/Dunkel-Umschalter speichert seine Auswahl
lokal; zunächst gilt das Farbschema des Betriebssystems.

Die Compose-Konfiguration enthält den eigenen Übersetzungsdienst LibreTranslate.
Er benötigt beim ersten Start Internetzugriff zum Laden der Sprachmodelle und kann
mehrere Minuten benötigen. Modelle bleiben im separaten Volume gespeichert; die
fertigen Übersetzungen werden in der AG-News-Datenbank zwischengespeichert.
Der Dienst hat keinen veröffentlichten Host-Port. Eine kostenpflichtige Übersetzungs-API
ist nicht erforderlich. `TRANSLATE_URL` muss aus dem App-Container erreichbar sein.
Bei einem vorhandenen eigenen LibreTranslate-Dienst kann dessen Adresse verwendet
werden. Ein externer Dienst erhält die zur Übersetzung angefragten Nachrichtentexte.

Automatisch übersetzte Texte sind gekennzeichnet; die Originalquelle bleibt verlinkt.
Ist die Übersetzung noch nicht verfügbar, zeigt die Anwendung den Originaltext mit
Hinweis. Die Übersetzungen ändern weder die gespeicherten Originalmeldungen noch
Quellenfilter und Suchindex: Die Suche arbeitet weiterhin mit den Originaltexten.
RSS liefert weiterhin die Originalmeldungen. Der erste Seitenaufruf mit neuen Texten
kann wegen der Übersetzung länger dauern; spätere Aufrufe nutzen den Cache.
