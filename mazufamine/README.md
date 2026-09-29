# MazufaMine 0.1 — ensimmäinen lukuversio

RainbowMinerin rinnalla toimiva paikallinen seuranta. Python 3.10 tai uudempi; ei ulkoisia Python-riippuvuuksia. Linux on ensisijainen kohde. Mukana on pieni itsenäinen dashboard ja tuotava Node-RED-virta. FlowFuse Dashboardia, CCXT:tä tai Hummingbotia ei vielä asenneta.

## Kokeile demoa

Lataa tämä haara ZIP-tiedostona GitHubin Code → Download ZIP -valinnalla, pura se ja avaa pääte `mazufamine`-kansiossa:

```bash
python3 app.py --demo
```

Avaa http://127.0.0.1:8787 . Windowsissa komento on tarvittaessa `py app.py --demo`. DEMO käyttää selvästi merkittyä esimerkkilaitetta eikä kysy RainbowMineriltä tietoja. Lopeta Ctrl+C:llä.

## Liitä käynnissä oleva RainbowMiner

```bash
cp config.example.json config.json
python3 app.py
```

Windowsissa kopioi `config.example.json` nimelle `config.json`. Muokkaa URL osoittamaan omaa RainbowMinerin rajapintaa (oletuksena localhost:4000). Useita rigejä voi lisätä `rigs`-listaan eri nimillä. Käytä vain omia luotettuja osoitteita. Rajapinnan tulee olla saavutettavissa tältä koneelta; sitä ei tarvitse julkaista internetiin. HTTP Basic Auth -tukea ei tässä versiossa ole. Autentikoitua tai vanhemman version rajapintaa ei kierretä: virhe näkyy näkymässä.

Palvelu kysyy vain `/getdevices`, `/runningminers`, `/currentprofit` ja `/balances`. Muita polkuja, uudelleenohjauksia tai kirjoituskomentoja ei sallita adapterissa. Jokainen osavastaus saa oman onnistumisajan ja virhetilan. Data vanhenee viimeistään 45 sekunnissa. Vastaukset esitetään alkuperäisinä JSON-tietoina, jotta tuntemattomia yksiköitä tai eri versioiden kenttiä ei tulkita väärin. Seuraava vaihe on niiden normalisointi oikean rigin havaintojen perusteella.

Dashboard palvelee vain osoitteessa 127.0.0.1. Se ei tarjoa etähallintaa tai käyttäjätunnuksia. Älä julkaise porttia käänteisellä välityspalvelimella sellaisenaan. Lokit eivät tulosta poolien vastauksia; dashboardissa voi silti näkyä omia pooli- tai lompakkotietoja. Havaintoja pidetään vain muistissa.

## Nettokassavirran kirjanpito

SQLite-tietokanta luodaan paikallisesti. Tuo itse todennettuja EUR-määräisiä tapahtumia CSV:stä:

```csv
id,occurred_at,kind,eur
exchange:fill:123,2026-09-29T12:00:00Z,sale_net,10.20
meter:2026-09-29,2026-09-29T23:00:00Z,electricity,2.10
```

```bash
python3 app.py --import-ledger oma_kirjanpito.csv
```

Tuetut lajit ovat `sale_net` (toteutunut myynti jo vähennettyine palkkioineen), `fee_extra` (vain vielä vähentämätön lisäkulu), `transfer` (siirtokulu) ja `electricity` (todellinen sähkökulu). Kaikki määrät ovat positiivisia EUR-lukuja. Aikaleima tarvitsee aikavyöhykkeen. Jokaisella tapahtumalla on pysyvä yksilöllinen tunniste. Sama tapahtuma voidaan tuoda uudestaan; samalle tunnisteelle muuttunut sisältö keskeyttää koko tuonnin ja peruu sen muutokset.

Tulos on tuodun aineiston nettokassavirta, ei automaattisesti täydellinen kirjanpito. Kaikkien kulujen mukanaoloa tai maksun aitoutta ei voida todistaa pelkästä CSV:stä. Jo nettomäärään sisältyvää palkkiota ei tuoda uudelleen. Myymätön saldo ja RBM:n tuottoarvio eivät tule tähän laskentaan. Esimerkkisummaa ei tuoda automaattisesti. Tietokanta ei ole veroraportti eikä tässä versiossa sisällä automaattista valuuttamuunnosta tai muokkauskäyttöliittymää.

## Node-RED

Tuo `node-red-flow.json` Node-REDin Import-toiminnolla. Virta hakee vain MazufaMinen `/api/status`-rajapinnan ja näyttää vastauksen Debug-paneelissa. Node-REDin tulee tässä esimerkissä olla samalla isännällä (kontin localhost on eri ympäristö). Tarkista URL ennen Deploy-toimintoa. Virta ei ohjaa louhintaa. Varsinainen FlowFuse-näkymä toteutetaan seuraavassa vaiheessa; nyt selainpaneeli tulee Python-palvelusta.

## Testit ja rajat

```bash
python3 -m unittest -v
```

Testattu: nettosumma, toistotuonti, ristiriidan transaktiopalautus, puuttuva data, NaN-hylkäys, katkon jälkeinen vanhentuminen ja kirjoituspolkujen esto. Lisäksi HTTP-demopalvelu tarkistettu. Oikeaa GPU:ta, poolimaksua tai pörssiä ei ole testattu. Tämä on ensimmäinen tekninen versio, ei koko MazufaMine-järjestelmän valmis julkaisu.

Seuraavat toteutukset: normalisoitu laitenäkymä ja seinämittauksen sähkökulu, coinien hyväksyntäketju, kahden GPU:n ohjaustesti, myyntisimulaatio ja vasta niiden jälkeen rajattu live-käyttö. Hummingbot, CCXT, amdgpu_top ja mining-pool-stats ovat edelleen erillisiä forkkeja.

Pidä `config.json`, CSV:t ja `ledger.sqlite3` omalla koneellasi. Älä commitoi avaimia tai taloustietoja. Ota tietokannasta varmuuskopio palvelun ollessa pysäytettynä. Tämä lisäosa jaetaan tämän RainbowMiner-forkin GPL-3.0-lisenssin mukaan; alkuperäisen projektin ilmoitukset säilyvät.
