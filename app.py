import os, re, time, html, hashlib, logging, threading
from datetime import datetime, timezone
from urllib.parse import urlparse
from email.utils import parsedate_to_datetime
import feedparser, httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

logging.basicConfig(level=logging.INFO)
DB=os.environ.get("DATABASE_URL","sqlite:////data/news.db")
engine=create_engine(DB, pool_pre_ping=True)
with engine.begin() as c:
    c.execute(text("""CREATE TABLE IF NOT EXISTS news (
      id VARCHAR(64) PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
      source TEXT NOT NULL, category TEXT NOT NULL, summary TEXT NOT NULL,
      published TIMESTAMP NOT NULL, added TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"""))
FEEDS=[
 ("CISA","https://www.cisa.gov/cybersecurity-advisories/all.xml","Sicherheit"),
 ("Microsoft Security","https://msrc.microsoft.com/blog/feed","Microsoft"),
 ("GitHub Security","https://github.blog/security/feed/","Sicherheit"),
 ("Proxmox","https://www.proxmox.com/en/about/company-details/press-releases/rss","Virtualisierung"),
]
KEYWORDS=re.compile(r"security|vulnerab|cve-|exploit|patch|ransomware|outage|incident|advisory|update|critical|windows|linux|firmware|schwachstell|sicherheits",re.I)
app=FastAPI(title="AG News",docs_url=None,redoc_url=None)
def safe(s,limit=1000):
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",str(s or ""))).strip()[:limit]
def poll():
    added=0
    with httpx.Client(timeout=18, follow_redirects=True, headers={"User-Agent":"AG-News/1.0"}) as client:
        for source,feed_url,category in FEEDS:
            try:
                response=client.get(feed_url)
                response.raise_for_status()
                feed=feedparser.parse(response.content)
                for item in feed.entries[:40]:
                    title=safe(item.get("title"),300)
                    link=item.get("link","")
                    if not title or not KEYWORDS.search(title) or urlparse(link).scheme!="https":
                        continue
                    raw=item.get("published") or item.get("updated")
                    try: published=parsedate_to_datetime(raw).astimezone(timezone.utc).replace(tzinfo=None) if raw else datetime.now(timezone.utc).replace(tzinfo=None)
                    except Exception: published=datetime.now(timezone.utc).replace(tzinfo=None)
                    if abs((datetime.utcnow()-published).total_seconds()) > 7*86400:
                        continue
                    summary=safe(item.get("summary") or item.get("description"),850)
                    uid=hashlib.sha256(link.encode()).hexdigest()
                    try:
                        with engine.begin() as c:
                            c.execute(text("INSERT INTO news (id,title,url,source,category,summary,published) VALUES (:id,:title,:url,:source,:category,:summary,:published)"),
                                dict(id=uid,title=title,url=link,source=source,category=category,summary=summary,published=published))
                        added+=1
                    except IntegrityError: pass
            except Exception: logging.exception("Feed-Fehler: %s",source)
    logging.info("News importiert: %d",added)
def loop():
    while True:
        try: poll()
        except Exception: logging.exception("Import fehlgeschlagen")
        time.sleep(3600)
@app.on_event("startup")
def start():
    threading.Thread(target=loop,daemon=True).start()
def page(content,title="AG News"):
    return HTMLResponse(f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Aktuelle IT-Sicherheits- und Infrastrukturmeldungen"><title>{html.escape(title)} | AG News</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#0b1020;color:#eaf0ff;font:16px system-ui,sans-serif;line-height:1.65}}header{{background:#111a30;border-bottom:1px solid #26334d;padding:18px max(20px,calc((100vw - 980px)/2))}}a{{color:#91c6ff}}nav a{{margin-right:18px}}.brand{{font-weight:800;font-size:26px;color:white;text-decoration:none}}main{{max-width:980px;margin:36px auto;padding:0 20px}}.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}}article{{background:#151f35;border:1px solid #293752;border-radius:14px;padding:20px}}article h2{{line-height:1.25;margin:8px 0}}article h2 a{{color:white;text-decoration:none}}small{{color:#a5b4ce}}.tag{{color:#6ed8bc;font-size:13px;font-weight:bold}}footer{{margin:70px auto 20px;max-width:980px;padding:20px;color:#a5b4ce;border-top:1px solid #293752}}input{{background:#1c2940;border:1px solid #40516a;color:white;padding:12px;border-radius:10px;width:min(100%,460px)}}</style></head><body><header><a class="brand" href="/">AG News</a><nav><a href="/">News</a><a href="/rss.xml">RSS</a></nav></header><main>{content}</main><footer>AG News · Automatisierter Nachrichtenüberblick · Quellen und Veröffentlichungszeiten beachten. <strong>Impressum und Datenschutz vor öffentlicher Freischaltung ergänzen!</strong></footer></body></html>""")
@app.get("/",response_class=HTMLResponse)
def index(q:str=""):
    with engine.connect() as c:
        if q:
            rows=c.execute(text("SELECT * FROM news WHERE lower(title) LIKE :q OR lower(summary) LIKE :q ORDER BY published DESC LIMIT 100"),{"q":"%"+q.lower()[:80]+"%"}).mappings().all()
        else: rows=c.execute(text("SELECT * FROM news ORDER BY published DESC LIMIT 100")).mappings().all()
    cards=""
    for r in rows:
        cards+=f'<article><span class="tag">{html.escape(r["category"])}</span><small> · {html.escape(r["source"])} · {r["published"]:%d.%m.%Y %H:%M} UTC</small><h2><a href="/article/{r["id"]}">{html.escape(r["title"])}</a></h2><p>{html.escape(r["summary"][:280])}</p></article>'
    return page(f'<h1>Aktuelle IT-Meldungen</h1><p>Offizielle Quellen, automatisiert stündlich geprüft. Noch keine KI-generierten Artikel.</p><form><input name="q" placeholder="Meldungen durchsuchen..." value="{html.escape(q,quote=True)}"></form><p>{len(rows)} Meldungen</p><div class="cards">{cards or "<p>Noch keine Meldungen vorhanden.</p>"}</div>')
@app.get("/article/{uid}",response_class=HTMLResponse)
def article(uid:str):
    if not re.fullmatch("[a-f0-9]{64}",uid): raise HTTPException(404)
    with engine.connect() as c: r=c.execute(text("SELECT * FROM news WHERE id=:id"),{"id":uid}).mappings().first()
    if not r:raise HTTPException(404)
    return page(f'<article><span class="tag">{html.escape(r["category"])}</span><h1>{html.escape(r["title"])}</h1><small>{html.escape(r["source"])} · {r["published"]:%d.%m.%Y %H:%M} UTC</small><p>{html.escape(r["summary"])}</p><p><a href="{html.escape(r["url"],quote=True)}" rel="noopener noreferrer" target="_blank">Originalquelle lesen</a></p><small>Automatischer Quellenüberblick, keine redaktionell unabhängig bestätigte Meldung.</small></article>',r["title"])
@app.get("/health")
def health():return {"ok":True}
@app.get("/rss.xml")
def rss():
    with engine.connect() as c: rows=c.execute(text("SELECT * FROM news ORDER BY published DESC LIMIT 50")).mappings().all()
    items="".join(f'<item><title>{html.escape(r["title"])}</title><link>{html.escape(r["url"])}</link><guid>{r["id"]}</guid><description>{html.escape(r["summary"])}</description></item>' for r in rows)
    return Response(f'<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>AG News</title><link>https://example.invalid</link><description>IT News</description>{items}</channel></rss>',media_type="application/rss+xml")
