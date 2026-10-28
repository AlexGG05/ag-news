import os, tempfile, unittest, re
from unittest.mock import patch
os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
os.environ.update(APP_BASE_URL='https://news.example.org',SMTP_HOST='smtp.example.org',SMTP_FROM='news@example.org')
import app
from fastapi.testclient import TestClient
from sqlalchemy import text

class Workflow(unittest.TestCase):
    def test_accounts_and_sources(self):
        with patch.object(app,'loop'), patch('auth.smtplib.SMTP') as smtp, TestClient(app.app,base_url='https://testserver') as c:
            def submit(path,**fields):
                c.get(path)
                return c.post(path,data={'csrf':c.cookies['ag_csrf'],**fields})
            protected_paths=['/', '/?q=Linux', '/article/'+'a'*64, '/rss.xml']
            def assert_locked():
                for path in protected_paths:
                    response=c.get(path,follow_redirects=False)
                    self.assertEqual(response.status_code,303)
                    self.assertEqual(response.headers['location'],'/login')
                    self.assertNotIn('Linux warning',response.text)
            assert_locked()
            c.cookies.set('ag_session','invalid')
            assert_locked()
            c.cookies.clear()
            r=submit('/register',email='test@example.org',password='long-password-123')
            self.assertIn('erhältst du eine E-Mail',r.text)
            mail=smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
            token=re.search(r'token=([\w-]+)',mail.get_content()).group(1)
            self.assertIn('Anmeldung nicht möglich',submit('/login',email='test@example.org',password='long-password-123').text)
            submit('/verify',token=token)
            self.assertIn('ungültig',submit('/verify',token=token).text)
            self.assertIn('Abmelden',submit('/login',email='test@example.org',password='long-password-123').text)
            self.assertEqual(c.post('/logout',data={'csrf':'wrong'}).status_code,403)
            submit('/forgot',email='test@example.org')
            mail=smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
            token=re.search(r'token=([\w-]+)',mail.get_content()).group(1)
            submit('/reset',token=token,password='new-long-password-456')
            self.assertNotIn('Abmelden',c.get('/').text)
            assert_locked()
            self.assertIn('ungültig',submit('/reset',token=token,password='new-long-password-456').text)
            self.assertIn('Abmelden',submit('/login',email='test@example.org',password='new-long-password-456').text)
            with app.engine.begin() as db:
                for uid,title,source in [('a'*64,'Linux warning','CERT-Bund WID'),('b'*64,'Microsoft update','Microsoft MSRC')]:
                    db.execute(text('INSERT INTO news(id,title,url,source,category,summary,published) VALUES (:id,:title,:url,:source,:category,:summary,:published)'),dict(id=uid,title=title,url='https://example.org',source=source,category='Security',summary='<script>alert(1)</script>',published='2026-10-28 10:00:00'))
            r=c.get('/',params={'source':'CERT-Bund WID','q':'Linux','category':'Security'})
            self.assertIn('Linux warning',r.text);self.assertNotIn('Microsoft update',r.text)
            self.assertIn('&lt;script&gt;',r.text)
            self.assertEqual(c.get('/article/'+'a'*64).status_code,200)
            self.assertEqual(c.get('/health').json(),{'ok':True})
            self.assertEqual(c.get('/rss.xml').status_code,200)
            from auth import digest
            with app.engine.begin() as db:
                db.execute(text('UPDATE sessions SET expires=0 WHERE token=:t'),{'t':digest(c.cookies['ag_session'])})
            assert_locked()
            submit('/login',email='test@example.org',password='new-long-password-456')
            with app.engine.connect() as db:
                csrf=db.execute(text('SELECT csrf FROM sessions WHERE token=:t'),{'t':digest(c.cookies['ag_session'])}).scalar_one()
            c.post('/logout',data={'csrf':csrf})
            assert_locked()

            self.assertEqual(c.post('/login',data={'email':'test@example.org'}).status_code,403)
            submit('/forgot',email='test@example.org')
            mail=smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
            expired=re.search(r'token=([\w-]+)',mail.get_content()).group(1)
            with app.engine.begin() as db: db.execute(text('UPDATE auth_tokens SET expires=0'))
            self.assertIn('ungültig',submit('/reset',token=expired,password='another-password-123').text)


class Languages(unittest.TestCase):
    def test_switch_and_translation_cache(self):
        with patch.object(app,'loop'), TestClient(app.app,base_url='https://testserver') as c:
            r=c.get('/language?lang=en&next=/',follow_redirects=True)
            self.assertIn('<html lang="en">',r.text)
            self.assertIn('Welcome back',r.text)
            self.assertIn('Create account',c.get('/register').text)
            self.assertIn('Verify email',c.get('/verify').text)
            self.assertEqual(c.get('/language?lang=fr').status_code,400)
            self.assertEqual(c.get('/language?lang=en&next=//evil.example',follow_redirects=False).headers['location'],'/')
            self.assertEqual(c.get('/theme.js').status_code,200)
            c.get('/language?lang=de')
            self.assertIn('Willkommen zurück',c.get('/').text)
        from translations import localize
        from i18n import language
        marker=language.set('de')
        try:
            with patch.dict(os.environ,TRANSLATE_URL='http://translator:5000'),patch('translations.httpx.post') as post:
                post.return_value.json.return_value={'translatedText':['Deutscher Titel','Deutsche Zusammenfassung']}
                rows=[{'title':'Unique English headline','summary':'Unique English summary'}]
                translated=localize(rows,app.engine)
                self.assertEqual(translated[0]['title'],'Deutscher Titel')
                self.assertEqual(localize(rows,app.engine)[0]['summary'],'Deutsche Zusammenfassung')
                self.assertEqual(post.call_count,1)
                post.side_effect=__import__('httpx').ConnectError('offline')
                self.assertIn('nicht verfügbar',localize([{'title':'uncached','summary':''}],app.engine)[0]['translation_note'])
        finally:language.reset(marker)

if __name__=='__main__': unittest.main()
