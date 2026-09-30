# Uptime-monitor

Een kleine monitor in Python die om de 10 minuten je websites controleert en je een melding stuurt via [ntfy.sh](https://ntfy.sh) zodra er iets verandert. De monitor draait gratis op GitHub Actions; je hebt geen eigen server nodig.

## Wat wordt gecontroleerd?

| Check | Wanneer is het een probleem? | Soort melding |
|---|---|---|
| **Storing** | HTTP-statuscode is niet 200, of er komt geen antwoord (timeout, verbindingsfout) | urgent |
| **Trefwoord** | het opgegeven trefwoord staat niet op de pagina (hoofdletterongevoelig) | hoog |
| **Traag** | responstijd boven `slow_seconds` (standaard 3 s) | waarschuwing |
| **SSL-certificaat** | certificaat verloopt binnen `ssl_warn_days` (standaard 14 dagen) of is ongeldig | waarschuwing |

Je krijgt **alleen een melding bij een statuswijziging**: één bericht als iets misgaat en één herstelmelding als het weer goed is. Een storing die een uur duurt geeft dus twee berichten, geen zes per uur. Elke check wordt apart bijgehouden, dus "traag" en "storing" zijn onafhankelijke meldingen.

## Bestanden

| Bestand | Doel |
|---|---|
| `config.yaml` | sites en instellingen |
| `monitor.py` | de monitor |
| `state.json` | laatst bekende status (wordt automatisch bijgewerkt, niet handmatig aanpassen) |
| `.github/workflows/monitor.yml` | GitHub Actions-workflow |
| `tests/` | tests |

## Instellen

### 1. ntfy kiezen

1. Installeer de ntfy-app op je telefoon (Android/iOS) of open <https://ntfy.sh/app>.
2. Kies een **lastig te raden topicnaam**, bijvoorbeeld `uptime-x7k2q9-mijnnaam`. Bij ntfy.sh kan iedereen die de naam kent meelezen en berichten sturen. De topicnaam werkt dus als een wachtwoord.
3. Abonneer je in de app op dat topic.

### 2. Topic als secret opslaan

Omdat deze repo publiek is, zet je de topicnaam **niet** in de code of in `config.yaml`, maar in een GitHub-secret:

1. Ga in je repo naar **Settings → Secrets and variables → Actions → New repository secret**.
2. Naam: `NTFY_TOPIC`. Waarde: je topicnaam.

### 3. Schrijfrechten voor de workflow

Ga naar **Settings → Actions → General → Workflow permissions** en kies **Read and write permissions**. De workflow vraagt zelf al `contents: write` aan, maar een organisatie of repo kan dit overrulen. Dit is nodig om `state.json` terug te committen.

### 4. Starten

Push de bestanden naar GitHub. Ga daarna naar **Actions → Uptime-monitor → Run workflow** om direct een run te starten. Daarna draait hij vanzelf elke 10 minuten.

## Een site toevoegen

Voeg een blokje toe aan `config.yaml`:

```yaml
sites:
  - name: Mijn nieuwe site
    url: https://voorbeeld.nl
    keyword: Welkom          # optioneel
    slow_seconds: 5          # optioneel: overschrijft de standaard voor alleen deze site
```

Optionele instellingen per site: `keyword`, `timeout`, `slow_seconds`, `ssl_warn_days`, `failures_before_alert`.

**Let op:** kies een trefwoord dat echt in de HTML van de pagina staat. Staat de tekst pas na het laden via JavaScript op de pagina, dan vindt de monitor hem niet en krijg je een valse melding.

## Valse alarmen beperken

Zet `failures_before_alert: 2` in `config.yaml`. Een site moet dan twee checks achter elkaar mislukken (dus ongeveer 10 minuten) voor je een melding krijgt. Een kort haperinkje van één check blijft dan onopgemerkt. Standaard staat dit op 1 (direct melden).

## Zelf testen

Je hebt Python 3.10 of nieuwer nodig.

```bash
pip install -r requirements.txt pytest
pytest                                 # tests voor de meldlogica
python monitor.py                      # echte check; zonder NTFY_TOPIC worden geen meldingen verstuurd
NTFY_TOPIC=mijn-testtopic python monitor.py   # met meldingen (op Windows PowerShell: $env:NTFY_TOPIC="mijn-testtopic")
```

Let op: `python monitor.py` schrijft ook `state.json`. Zonder `NTFY_TOPIC` wordt de status van een probleem niet opgeslagen, zodat de melding bij de eerstvolgende run met topic alsnog komt. Wil je een schone start, zet dan de inhoud van `state.json` terug naar `{"sites": {}}`.

## Goed om te weten

- **Timing is niet exact.** GitHub start geplande workflows soms pas 5 tot 15 minuten later, vooral op drukke momenten. "Elke 10 minuten" is dus een streven.
- **Geplande workflows kunnen na 60 dagen zonder activiteit worden uitgezet.** GitHub doet dit in repo's waar niets gebeurt. Omdat de monitor alleen commit bij een statuswijziging, kan een rustige repo in die situatie komen. Merk je dat de meldingen wegblijven, kijk dan onder **Actions** of de workflow nog actief is en zet hem zo nodig weer aan. Een commit (bijvoorbeeld een kleine README-wijziging) per maand houdt hem actief.
- **`state.json` is publiek.** Hij bevat alleen de site-URL's, ok/probleem en het tijdstip van de laatste wijziging, dus geen geheimen. Wel kan iedereen zien wanneer je sites storing hadden.
- **Mislukt het versturen van een melding**, dan wordt de status niet opgeslagen en probeert de volgende run het opnieuw.
- **Kan de monitor zelf niet bij ntfy of GitHub**, dan hoor je niets. Voor kritieke sites is een tweede, onafhankelijke monitor een goede aanvulling.
