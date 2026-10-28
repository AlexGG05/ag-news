import os, re, time, html, hashlib, logging, threading
from datetime import datetime, timezone
from urllib.parse import urlparse
from email.utils import parsedate_to_datetime
import feedparser, httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, FileResponse, RedirectResponse
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
from sources import FEEDS, KEV_JSON

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
                    if not title or urlparse(link).scheme!="https":
                        continue
                    raw=item.get("published") or item.get("updated")
                    try: published=parsedate_to_datetime(raw).astimezone(timezone.utc).replace(tzinfo=None) if raw else datetime.now(timezone.utc).replace(tzinfo=None)
                    except Exception: published=datetime.now(timezone.utc).replace(tzinfo=None)
                    if abs((datetime.utcnow()-published).total_seconds()) > 14*86400:
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
        try:
            kev=client.get(KEV_JSON)
            kev.raise_for_status()
            data=kev.json()
            for item in data.get("vulnerabilities",[]):
                try:
                    day=item.get("dateAdded","")
                    if (datetime.now(timezone.utc).date()-datetime.strptime(day,"%Y-%m-%d").date()).days > 14:
                        continue
                    cve=item.get("cveID","")
                    if not re.fullmatch(r"CVE-\d{4}-\d{4,}",cve):
                        continue
                    title=safe(f"{cve}: {item.get('vendorProject','')} {item.get('product','')} – aktiv ausgenutzt",300)
                    link="https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
                    summary=safe(f"{item.get('vulnerabilityName','')}. {item.get('shortDescription','')} Maßnahme: {item.get('requiredAction','')}. Frist: {item.get('dueDate','')}.",850)
                    uid=hashlib.sha256(("kev:"+cve).encode()).hexdigest()
                    with engine.begin() as c:
                        c.execute(text("INSERT INTO news (id,title,url,source,category,summary,published) VALUES (:id,:title,:url,:source,:category,:summary,:published)"),dict(id=uid,title=title,url=link,source="CISA KEV",category="Aktiv ausgenutzt",summary=summary,published=datetime.strptime(day,"%Y-%m-%d")))
                    added+=1
                except IntegrityError:
                    pass
                except Exception:
                    logging.exception("KEV-Eintrag fehlgeschlagen")
        except Exception:
            logging.exception("CISA KEV Import fehlgeschlagen")
    logging.info("News importiert: %d",added)
def loop():
    while True:
        try: poll()
        except Exception: logging.exception("Import fehlgeschlagen")
        time.sleep(max(300, int(os.environ.get('POLL_INTERVAL_SECONDS', '1800'))))
@app.on_event("startup")
def start():
    threading.Thread(target=loop,daemon=True).start()
from starlette.concurrency import run_in_threadpool
from pathlib import Path
from ui import page as render_page, esc

@app.get("/theme.js", include_in_schema=False)
def theme_script():
    return FileResponse(Path(__file__).with_name("theme.js"), media_type="text/javascript")

from auth import install
install(app, engine)
from i18n import language, return_path
from translations import install as install_translations, localize
install_translations(engine)

@app.get("/language")
def choose_language(lang:str="de",next:str="/"):
    if lang not in ("de","en"): raise HTTPException(400)
    if not next.startswith("/") or next.startswith("//") or "\\" in next or any(ord(c)<32 for c in next): next="/"
    response=RedirectResponse(next,303)
    response.set_cookie("ag_language",lang,max_age=31536000,samesite="lax",httponly=True)
    return response


@app.middleware("http")
async def security_headers(request, call_next):
    selected=request.cookies.get("ag_language","de")
    locale_token=language.set(selected if selected in ("de","en") else "de")
    path_token=return_path.set(str(request.url.path)+("?"+request.url.query if request.url.query else ""))
    try:
        protected = request.url.path in ("/", "/rss.xml") or request.url.path.startswith("/article/")
        if protected and not await run_in_threadpool(app.state.current_user, request):
            response = RedirectResponse("/login", 303)
        else:
            response = await call_next(request)
    finally:
        language.reset(locale_token)
        return_path.reset(path_token)
    response.headers["Content-Language"]=selected if selected in ("de","en") else "de"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    response.headers["Cache-Control"] = "no-store"
    return response

def page(content,title="AG News",request=None):
    user=app.state.current_user(request) if request else None
    return HTMLResponse(render_page(content,title,user,user['csrf'] if user else ''))

def date_label(value):
    if isinstance(value,str): value=datetime.fromisoformat(value)
    return value.strftime('%d.%m.%Y · %H:%M UTC')

@app.get("/",response_class=HTMLResponse)
def index(request:Request,q:str="",source:str="",category:str=""):
    q=q[:100];source=source[:150];category=category[:150]
    clauses=[];params={}
    if q:
        clauses.append('(lower(title) LIKE :q OR lower(summary) LIKE :q)');params['q']='%'+q.lower()+'%'
    if source: clauses.append('source=:source');params['source']=source
    if category: clauses.append('category=:category');params['category']=category
    with engine.connect() as c:
        rows=c.execute(text('SELECT * FROM news'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY published DESC LIMIT 100'),params).mappings().all()
        sources=sorted({r[0] for r in c.execute(text('SELECT DISTINCT source FROM news'))}|{f[0] for f in FEEDS}|{'CISA KEV'})
        categories=sorted({r[0] for r in c.execute(text('SELECT DISTINCT category FROM news'))}|{f[2] for f in FEEDS}|{'Aktiv ausgenutzt'})
    rows=localize(rows,engine)
    def options(values,selected):
        return ''.join(f'<option value="{esc(v)}" {"selected" if v==selected else ""}>{esc(v)}</option>' for v in values)
    cards=''.join(f'<article><span class="tag">{esc(r["category"])}</span><h2><a href="/article/{esc(r["id"])}">{esc(r["title"])}</a></h2><p>{esc(r["summary"][:250])}</p><small>{esc(r["translation_note"])}</small><div class="cardfoot"><strong class="meta">{esc(r["source"])}</strong><span class="meta">{date_label(r["published"])}</span></div></article>' for r in rows)
    if not cards: cards='<div class="empty"><h2>Keine Meldungen gefunden</h2><p>Ändere deine Filter oder schaue später wieder vorbei.</p><a href="/">Alle Meldungen anzeigen →</a></div>'
    return page(f'''<span class="eyebrow">IT & Sicherheit · Der Quellenüberblick</span><h1>Wissen, was die IT bewegt.</h1><p class="intro">Aktuelle Sicherheitswarnungen, Updates und Infrastruktur-News. An einem Ort, direkt aus den Quellen.</p><form class="filters" method="get"><label>Suche<input name="q" placeholder="Thema, Produkt oder CVE suchen …" value="{esc(q)}"></label><label>Quelle<select name="source"><option value="">Alle Quellen</option>{options(sources,source)}</select></label><label>Thema<select name="category"><option value="">Alle Themen</option>{options(categories,category)}</select></label><button>Filtern</button></form><div class="results"><strong>{len(rows)} Meldungen{ ' · maximal 100' if len(rows)==100 else ''}</strong><a href="/">Filter zurücksetzen</a></div><div class="cards">{cards}</div>''',request=request)

@app.get("/article/{uid}",response_class=HTMLResponse)
def article(uid:str,request:Request):
    if not re.fullmatch('[a-f0-9]{64}',uid): raise HTTPException(404)
    with engine.connect() as c: r=c.execute(text('SELECT * FROM news WHERE id=:id'),{'id':uid}).mappings().first()
    if not r: raise HTTPException(404)
    r=localize([r],engine)[0]
    return page(f'''<div class="reading"><p><a href="/">← Zur Übersicht</a></p><article><span class="tag">{esc(r['category'])}</span><h1>{esc(r['title'])}</h1><div class="meta">{esc(r['source'])} · {date_label(r['published'])}</div><p>{esc(r['summary'])}</p><small>{esc(r['translation_note'])}</small><p><a class="button" href="{esc(r['url'])}" rel="noopener noreferrer" target="_blank">Originalquelle lesen ↗</a></p><small>Automatischer Quellenüberblick. Nicht unabhängig redaktionell bestätigt.</small></article></div>''',r['title'],request)

@app.get("/health")
def health():return {"ok":True}
@app.get("/rss.xml")
def rss():
    with engine.connect() as c: rows=c.execute(text("SELECT * FROM news ORDER BY published DESC LIMIT 50")).mappings().all()
    items="".join(f'<item><title>{esc(r["title"])}</title><link>{esc(r["url"])}</link><guid>{r["id"]}</guid><description>{esc(r["summary"])}</description></item>' for r in rows)
    return Response(f'<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>AG News</title><link>https://example.invalid</link><description>IT News</description>{items}</channel></rss>',media_type="application/rss+xml")
