"""Optional self-hosted LibreTranslate, with persistent source-sensitive caching."""
import hashlib, logging, os
import httpx
from sqlalchemy import text
from i18n import language

def install(engine):
    with engine.begin() as c:
        c.execute(text('CREATE TABLE IF NOT EXISTS translations (cache_key VARCHAR(64) PRIMARY KEY, translated TEXT NOT NULL)'))

def localize(rows,engine):
    endpoint=os.getenv('TRANSLATE_URL','').rstrip('/')
    target=language.get(); result=[dict(r) for r in rows];missing={};cached={}
    for row in result:
        for field in ('title','summary'):
            value=row[field]
            if not value:continue
            key=hashlib.sha256((target+'\0'+value).encode()).hexdigest()
            with engine.connect() as c: found=c.execute(text('SELECT translated FROM translations WHERE cache_key=:k'),{'k':key}).scalar()
            if found is not None:cached[key]=found
            else:missing[key]=value
    if missing and endpoint:
        try:
            keys=list(missing)
            # Bound each batch; a single request timeout also bounds page latency.
            response=httpx.post(endpoint+'/translate',json={'q':[missing[k] for k in keys],'source':'auto','target':target,'format':'text'},timeout=20)
            response.raise_for_status();values=response.json()['translatedText']
            if not isinstance(values,list) or len(values)!=len(keys) or not all(isinstance(v,str) and v for v in values):raise ValueError('Invalid translation response')
            with engine.begin() as c:
                for key,value in zip(keys,values):
                    c.execute(text('INSERT INTO translations(cache_key,translated) VALUES (:k,:v) ON CONFLICT(cache_key) DO NOTHING'),{'k':key,'v':value})
                    cached[key]=value
        except (httpx.HTTPError,ValueError,KeyError):logging.warning('Translation service unavailable; showing original text')
    for row in result:
        complete=True
        for field in ('title','summary'):
            if not row[field]:continue
            key=hashlib.sha256((target+'\0'+row[field]).encode()).hexdigest()
            if key in cached:row[field]=cached[key]
            else:complete=False
        row['translation_note']='Automatisch übersetzt · Original bei der Quelle' if complete else ('Originaltext · Übersetzung derzeit nicht verfügbar' if endpoint else 'Originaltext · Übersetzungsdienst nicht eingerichtet')
    return result
