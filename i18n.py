from contextvars import ContextVar
from html import escape
from html.parser import HTMLParser
import re
language = ContextVar('language', default='de')
return_path = ContextVar('return_path', default='/')
TRANSLATIONS = {
'Übersicht':'Overview','Anmelden':'Sign in','Konto erstellen':'Create account','Abmelden':'Sign out',
'Dein AG News Konto':'Your AG News account','Willkommen zurück':'Welcome back','E-Mail-Adresse':'Email address','Passwort':'Password',
'Passwort vergessen?':'Forgot your password?','Passwort vergessen':'Forgot password','Neues Passwort':'New password','E-Mail bestätigen':'Verify email',
'Bestätigungslink senden':'Send verification link','Link anfordern':'Request link','Passwort speichern':'Save password','Zur Anmeldung':'Back to sign in',
'Mindestens 12 Zeichen. Verwende ein eigenes, langes Passwort.':'At least 12 characters. Use a unique, long password.',
'Bitte eine gültige E-Mail-Adresse eingeben.':'Please enter a valid email address.',
'Das Passwort muss 12 bis 256 Zeichen lang sein.':'Your password must contain 12 to 256 characters.',
'Der Mailversand ist noch nicht eingerichtet. Bitte später erneut versuchen.':'Email delivery has not been configured yet. Please try again later.',
'Mailversand momentan nicht verfügbar. Bitte später erneut versuchen.':'Email delivery is currently unavailable. Please try again later.',
'Wenn die Adresse für diesen Vorgang infrage kommt, erhältst du eine E-Mail. Prüfe auch deinen Spamordner.':'If this address is eligible, you will receive an email. Please also check your spam folder.',
'Anmeldung nicht möglich. Prüfe deine Zugangsdaten und bestätige deine E-Mail-Adresse.':'Unable to sign in. Check your credentials and verify your email address.',
'Anmeldung nicht möglich.':'Unable to sign in.',
'Erfolgreich. Du kannst dich jetzt anmelden.':'Success. You can now sign in.',
'Dieser Link ist ungültig oder abgelaufen. Bitte einen neuen anfordern.':'This link is invalid or has expired. Please request a new one.',
'IT & Sicherheit · Der Quellenüberblick':'IT & security · Source overview','Wissen, was die IT bewegt.':'Stay ahead of what moves IT.',
'Aktuelle Sicherheitswarnungen, Updates und Infrastruktur-News. An einem Ort, direkt aus den Quellen.':'Security alerts, updates and infrastructure news. In one place, straight from the sources.',
'Suche':'Search','Thema, Produkt oder CVE suchen …':'Search topics, products or CVEs …','Quelle':'Source','Alle Quellen':'All sources','Thema':'Topic','Alle Themen':'All topics','Filtern':'Filter','Filter zurücksetzen':'Reset filters',
'Keine Meldungen gefunden':'No news found','Ändere deine Filter oder schaue später wieder vorbei.':'Try different filters or check back later.',
'Alle Meldungen anzeigen →':'View all news →','← Zur Übersicht':'← Back to overview','Originalquelle lesen ↗':'Read original source ↗',
'Automatischer Quellenüberblick. Nicht unabhängig redaktionell bestätigt.':'Automated source summary. Not independently verified by an editorial team.',
'AG News · Dein Überblick über IT & Sicherheit':'AG News · Your IT & security overview',
'Automatischer Quellenüberblick. Meldungen anhand der Originalquelle prüfen. Impressum und Datenschutz vor öffentlicher Freischaltung ergänzen.':'Automated source overview. Check the original sources. Add legal and privacy notices before public launch.',
'Aktiv ausgenutzt':'Actively exploited','Netzwerk':'Networking','Virtualisierung':'Virtualization',
'Automatisch übersetzt · Original bei der Quelle':'Machine translated · Original available from source',
'Originaltext · Übersetzung derzeit nicht verfügbar':'Original text · Translation currently unavailable',
'Originaltext · Übersetzungsdienst nicht eingerichtet':'Original text · Translation service not configured',
}
def tr(value):
    if language.get()!='en': return value
    if value in TRANSLATIONS: return TRANSLATIONS[value]
    return re.sub(r'^(\d+) Meldungen( · maximal 100)?$',lambda m:m[1]+' articles'+(' · up to 100' if m[2] else ''),value)
class Translator(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True);self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('style','script'):self.skip+=1
        if tag=='html':attrs=[(k,'en' if k=='lang' else v) for k,v in attrs]
        self.parts.append('<'+tag+''.join(' '+k+('="'+escape(tr(v) if k in ('placeholder','aria-label','title') else v,quote=True)+'"' if v is not None else '') for k,v in attrs)+'>')
    def handle_endtag(self,tag):
        if tag in ('style','script'):self.skip-=1
        self.parts.append('</'+tag+'>')
    def handle_data(self,data):
        self.parts.append(data if self.skip else escape(tr(data),quote=False))
    def handle_entityref(self,name):self.parts.append('&'+name+';')
    def handle_charref(self,name):self.parts.append('&#'+name+';')
    def handle_decl(self,decl):self.parts.append('<!'+decl+'>')
def translate_html(content):
    if language.get()=='de':return content
    parser=Translator();parser.feed(content);return ''.join(parser.parts)
