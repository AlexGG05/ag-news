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
            self.assertEqual(c.post('/login',data={'email':'test@example.org'}).status_code,403)
            submit('/forgot',email='test@example.org')
            mail=smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
            expired=re.search(r'token=([\w-]+)',mail.get_content()).group(1)
            with app.engine.begin() as db: db.execute(text('UPDATE auth_tokens SET expires=0'))
            self.assertIn('ungültig',submit('/reset',token=expired,password='another-password-123').text)

if __name__=='__main__': unittest.main()
