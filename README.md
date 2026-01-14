# NoSocial.life

Privāta mājas mākoņkrātuve + Home Media Server (DLNA/UPnP), ko var uzstādīt uz sava servera un izmantot kā bezmaksas alternatīvu komerciāliem “cloud” risinājumiem.

##  Kas tas ir?
**NoSocial.life** ir tīmekļa lietotne failu glabāšanai un piekļuvei tiem no jebkuras vietas pasaulē. Visi dati tiek glabāti lietotāja mājas serverī, nevis trešo pušu infrastruktūrā, tāpēc lietotājs saglabā pilnu kontroli pār failiem un krātuves apjomu.

Papildus “cloud storage” funkcijām sistēma piedāvā **Movies** direktoriju lokālajā tīklā, kas ļauj skatīties MP4 filmas televizorā, izmantojot **DLNA/UPnP**.

##  Galvenās funkcijas
- Reģistrācija un autorizācija (paroles hešošana)
- Failu augšupielāde uz serveri
- Failu lejupielāde no jebkuras vietas (attālināta piekļuve)
- Ērts File Explorer UI (mapju struktūra, vizuāla navigācija)
- Meklēšana pēc failu/mapju nosaukumiem
- Home Media Server (DLNA/UPnP) priekš MP4 filmām mapē **Movies**

##  Papildfunkcijas (plānā / pēc laika)
- Failu koplietošana (share) ar citiem lietotājiem vai ar saiti
- Publiskās mapes
- Failu priekšskatījumi (piem. attēli, PDF, TXT u.c.)
- Video skatīšanās pārlūkā (streaming)
- Failu šifrēšana diskā

##  Lietotāju tipi
- **Admin** — pārvalda lietotājus un sistēmas iestatījumus
- **User** — strādā ar saviem failiem (privāti faili pēc noklusējuma)

> **Movies** direktorija ir paredzēta koplietojamam multimediju saturam lokālajā tīklā.

##  Datu glabāšana
- Metadati par failiem un mapēm tiek glabāti **MySQL** datubāzē:
  - nosaukums, izmērs, unikāls ID, datums, autors, ceļš uz failu, preview ceļš
- Faili fiziski tiek saglabāti servera diskos (HDD)
- Failu sadales algoritms izvēlas disku ar vislielāko brīvo vietu, lai vieta tiktu izmantota vienmērīgi

##  Tehnoloģijas
**Backend**
- Python, FastAPI
- asyncmy (MySQL asinhronai darbībai)
- passlib (paroļu hešošanai)
- Jinja (šabloniem)

**Frontend**
- HTML, CSS, JavaScript

**Serveris**
- Ubuntu Linux (mājas serveris)
- domēns `nosocial.life`, plānots HTTPS

##  Mērķis
Izveidot stabilu, ātru un ērtu mājas “personal cloud” sistēmu, kas ļauj:
- piekļūt failiem no jebkuras vietas,
- glabāt datus privāti (paša serverī),
- skatīties filmas televizorā lokālajā tīklā bez USB/kabeļiem.