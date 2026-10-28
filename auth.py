import hashlib, hmac, os, secrets, smtplib, ssl, time
from email.message import EmailMessage
from urllib.parse import parse_qs
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from ui import page, esc

COOKIE='ag_session'
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def password_hash(password):
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def password_ok(password,stored):
    salt,expected=stored.split(':')
    return hmac.compare_digest(hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex(),expected)

def install(app,engine):
    with engine.begin() as c:
        for sql in [
            'CREATE TABLE IF NOT EXISTS users (email VARCHAR(254) PRIMARY KEY, password TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0)',
            'CREATE TABLE IF NOT EXISTS auth_tokens (token VARCHAR(64) PRIMARY KEY, email VARCHAR(254) NOT NULL, purpose VARCHAR(16) NOT NULL, expires BIGINT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS sessions (token VARCHAR(64) PRIMARY KEY, email VARCHAR(254) NOT NULL, csrf VARCHAR(64) NOT NULL, expires BIGINT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS auth_limits (key VARCHAR(64) PRIMARY KEY, hits INTEGER NOT NULL, expires BIGINT NOT NULL)']:
            c.execute(text(sql))
    def current(request):
        with engine.connect() as c:
            return c.execute(text('SELECT email,csrf FROM sessions WHERE token=:t AND expires>:now'),{'t':digest(request.cookies.get(COOKIE,'')),'now':int(time.time())}).mappings().first()
    app.state.current_user=current
    def secure(): return os.getenv('APP_BASE_URL','http://localhost:8080').startswith('https://')
    def form(request,kind,message='',error=False,token=''):
        names={'login':'Willkommen zurück','register':'Konto erstellen','forgot':'Passwort vergessen?','reset':'Neues Passwort','verify':'E-Mail bestätigen'}
        csrf=secrets.token_urlsafe(32)
        fields=f'<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="token" value="{esc(token)}">'
        if kind in ('login','register','forgot'): fields+='<label>E-Mail-Adresse<input name="email" type="email" autocomplete="email" maxlength="254" required></label>'
        if kind in ('login','register','reset'): fields+='<label>Passwort<input name="password" type="password" autocomplete="'+('current-password' if kind=='login' else 'new-password')+'" minlength="12" maxlength="256" required></label>'
        if kind in ('register','reset'): fields+='<p class="meta">Mindestens 12 Zeichen. Verwende ein eigenes, langes Passwort.</p>'
        labels={'login':'Anmelden','register':'Bestätigungslink senden','forgot':'Link anfordern','reset':'Passwort speichern','verify':'E-Mail bestätigen'}
        note=f'<p role="status" class="notice {"error" if error else ""}">{esc(message)}</p>' if message else ''
        content=f'<section class="auth"><span class="eyebrow">Dein AG News Konto</span><h1>{names[kind]}</h1>{note}<form method="post" action="/{kind}">{fields}<button>{labels[kind]}</button></form><p><a href="/login">Zur Anmeldung</a> · <a href="/forgot">Passwort vergessen</a></p></section>'
        r=HTMLResponse(page(content,names[kind]));r.set_cookie('ag_csrf',csrf,httponly=True,secure=secure(),samesite='strict',max_age=3600);return r
    def send(email,purpose):
        base=os.getenv('APP_BASE_URL','').rstrip('/')
        host=os.getenv('SMTP_HOST');sender=os.getenv('SMTP_FROM')
        if not host or not sender or not base: raise RuntimeError('Mailversand ist noch nicht konfiguriert.')
        token=secrets.token_urlsafe(32)
        with engine.begin() as c:
            c.execute(text('DELETE FROM auth_tokens WHERE email=:e AND purpose=:p'),{'e':email,'p':purpose})
            c.execute(text('INSERT INTO auth_tokens VALUES (:t,:e,:p,:x)'),{'t':digest(token),'e':email,'p':purpose,'x':int(time.time())+(3600 if purpose=='verify' else 1800)})
        msg=EmailMessage();msg['From']=sender;msg['To']=email
        msg['Subject']='AG News: '+('E-Mail bestätigen' if purpose=='verify' else 'Passwort zurücksetzen')
        msg.set_content(f'Öffne diesen Link, um deine Anfrage abzuschließen:\n{base}/{purpose}?token={token}\n\nDer Link ist einmalig und '+('60' if purpose=='verify' else '30')+' Minuten gültig. Falls du dies nicht angefordert hast, ignoriere diese Nachricht.')
        port=int(os.getenv('SMTP_PORT','587'))
        with smtplib.SMTP(host,port,timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.getenv('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
            smtp.send_message(msg)
    async def handle(request:Request):
        kind=request.url.path.strip('/')
        if request.method=='GET': return form(request,kind,token=request.query_params.get('token',''))
        raw=await request.body()
        if len(raw)>4096: return HTMLResponse('Anfrage zu groß',413)
        data={k:v[0] for k,v in parse_qs(raw.decode()).items()}
        csrf=data.get('csrf','')
        if not csrf or not hmac.compare_digest(csrf,request.cookies.get('ag_csrf','')): return HTMLResponse('Formular abgelaufen. Bitte neu laden.',403)
        now=int(time.time());key=digest((request.client.host if request.client else 'unknown')+':'+kind)
        with engine.begin() as c:
            c.execute(text('DELETE FROM auth_limits WHERE expires<:n'),{'n':now})
            c.execute(text('INSERT INTO auth_limits (key,hits,expires) VALUES (:k,0,:x) ON CONFLICT (key) DO NOTHING'),{'k':key,'x':now+900})
            hits=c.execute(text('UPDATE auth_limits SET hits=hits+1 WHERE key=:k RETURNING hits'),{'k':key}).scalar_one()
        if hits>20: return HTMLResponse('Zu viele Versuche. Bitte in 15 Minuten erneut versuchen.',429)
        email=data.get('email','').strip().lower();password=data.get('password','');token=data.get('token','')
        if kind in ('register','forgot','login'):
            import re
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254: return form(request,kind,'Bitte eine gültige E-Mail-Adresse eingeben.',True)
        if kind in ('register','reset') and not 12<=len(password)<=256: return form(request,kind,'Das Passwort muss 12 bis 256 Zeichen lang sein.',True,token)
        if kind in ('register','forgot'):
            if not all(os.getenv(k) for k in ('SMTP_HOST','SMTP_FROM','APP_BASE_URL')): return form(request,kind,'Der Mailversand ist noch nicht eingerichtet. Bitte später erneut versuchen.',True)
            with engine.connect() as c: user=c.execute(text('SELECT * FROM users WHERE email=:e'),{'e':email}).mappings().first()
            if kind=='register' and not user:
                try:
                    with engine.begin() as c: c.execute(text('INSERT INTO users(email,password) VALUES (:e,:p)'),{'e':email,'p':password_hash(password)})
                except IntegrityError: pass
            try:
                if kind=='register' and (not user or not user['verified']): send(email,'verify')
                if kind=='forgot' and user and user['verified']: send(email,'reset')
            except (OSError,smtplib.SMTPException,RuntimeError):
                return form(request,kind,'Mailversand momentan nicht verfügbar. Bitte später erneut versuchen.',True)
            return form(request,kind,'Wenn die Adresse für diesen Vorgang infrage kommt, erhältst du eine E-Mail. Prüfe auch deinen Spamordner.')
        if kind=='login':
            if len(password)>256: return form(request,kind,'Anmeldung nicht möglich.',True)
            with engine.connect() as c: user=c.execute(text('SELECT * FROM users WHERE email=:e'),{'e':email}).mappings().first()
            candidate=password[:256]
            valid=password_ok(candidate,user['password'] if user else password_hash('dummy-password'))
            if not user or not valid or not user['verified']: return form(request,kind,'Anmeldung nicht möglich. Prüfe deine Zugangsdaten und bestätige deine E-Mail-Adresse.',True)
            session=secrets.token_urlsafe(32)
            with engine.begin() as c:
                c.execute(text('DELETE FROM sessions WHERE expires<:n'),{'n':now})
                c.execute(text('INSERT INTO sessions VALUES (:t,:e,:c,:x)'),{'t':digest(session),'e':email,'c':secrets.token_urlsafe(32),'x':now+604800})
            r=RedirectResponse('/',303);r.set_cookie(COOKIE,session,httponly=True,secure=secure(),samesite='lax',max_age=604800);return r
        if kind in ('verify','reset'):
            with engine.begin() as c:
                row=c.execute(text('DELETE FROM auth_tokens WHERE token=:t AND purpose=:p AND expires>:n RETURNING email'),{'t':digest(token),'p':kind,'n':now}).first()
                if row:
                    if kind=='verify': c.execute(text('UPDATE users SET verified=1 WHERE email=:e'),{'e':row[0]})
                    else:
                        c.execute(text('UPDATE users SET password=:p WHERE email=:e'),{'p':password_hash(password),'e':row[0]})
                        c.execute(text('DELETE FROM sessions WHERE email=:e'),{'e':row[0]})
            return form(request,'login','Erfolgreich. Du kannst dich jetzt anmelden.' if row else 'Dieser Link ist ungültig oder abgelaufen. Bitte einen neuen anfordern.',not bool(row))
    for path in ('login','register','forgot','reset','verify'): app.add_api_route('/'+path,handle,methods=['GET','POST'])
    @app.post('/logout')
    async def logout(request:Request):
        user=current(request);data=parse_qs((await request.body()).decode())
        if not user or not hmac.compare_digest(data.get('csrf',[''])[0],user['csrf']): return HTMLResponse('Ungültige Anfrage',403)
        with engine.begin() as c:c.execute(text('DELETE FROM sessions WHERE token=:t'),{'t':digest(request.cookies.get(COOKIE,''))})
        r=RedirectResponse('/',303);r.delete_cookie(COOKIE);return r
