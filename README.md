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
    depends_on:
      db:
        condition: service_healthy

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
```

Danach unter `http://SERVER-IP:8089` öffnen. Für öffentlichen Betrieb HTTPS per Nginx Proxy Manager/Cloudflare konfigurieren. **Vor produktivem Einsatz** das Beispielpasswort in beiden Umgebungsvariablen ändern (identischer neuer Wert; bei bereits initialisierter Datenbank zusätzlich das PostgreSQL-Passwort migrieren).

## Automatische Aktualisierung

Der Import läuft **beim Containerstart und danach stündlich**. Der Dienst liest ausgewählte Feeds (CISA, Microsoft Security, GitHub Security, Proxmox), filtert Schlagwörter und speichert Titel, Zusammenfassung, Datum und Quelle. Die Webseite zeigt neue Meldungen sofort beim erneuten Laden; kein Git-Push oder Image-Update pro Nachricht erforderlich. Der Import garantiert nicht, dass alle Feeds erreichbar oder vollständig sind.

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
