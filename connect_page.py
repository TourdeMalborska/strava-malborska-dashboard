"""
Athlete-facing "connect your device" landing page, with the consent step.

Mobile-first. Page shell follows the organization branding of
szkolaprzymalborskiej.pl (light theme; red #f44336 + gold #ffd740; Montserrat +
Roboto). Provider buttons keep each provider's OWN brand color.

CONSENT (Strava API Policy 2.1 / 7.2): before any provider data is accessed the
user must be told (i) what data is collected, (ii) how it is collected, (iii) how
to withdraw consent, (iv) how to request deletion, and (v) that deletion is
confirmed. The text below discloses all of that, and the provider buttons sit
inside a <form> with a REQUIRED checkbox: the browser refuses to submit until it
is ticked. The server re-checks (`consent=1`) in the /auth/<provider> routes.

Languages: Polish (default) and English (?lang=en).
"""

# (label, provider slug, auth path or None, brand color, status)
PROVIDERS = [
    ("Strava",           "strava", "/auth/strava", "#FC4C02", "live"),
    ("COROS",            "coros",  "/auth/coros",  "#000000", "live"),
    ("Wahoo",            "wahoo",  "/auth/wahoo",  "#1E73BE", "live"),
    ("Garmin Connect",   "garmin", None,           "#007CC3", "soon"),
    ("Polar",            "polar",  None,           "#E4002B", "soon"),
    ("Hammerhead Karoo", "karoo",  None,           "#111827", "soon"),
    ("Suunto",           "suunto", None,           "#1A1A1A", "soon"),
]

TEXT = {
    "pl": {
        "html_lang": "pl",
        "title": "Tour de Malborska — Połącz urządzenie",
        "tagline": "Połącz swoje konto sportowe, aby dołączyć do klubowego rankingu kilometrów.",
        "need_consent": "Aby kontynuować, zapoznaj się z informacją poniżej i zaznacz zgodę.",
        "consent_title": "Zanim połączysz konto",
        "consent_intro": "Przeczytaj, jak przetwarzamy Twoje dane:",
        "items": [
            ("Jakie dane pobieramy:",
             "imię i nazwisko (lub pseudonim) z Twojego konta, płeć (jeśli jest podana) "
             "oraz dla każdej aktywności: datę, rodzaj sportu, dystans, czas ruchu, nazwę "
             "i informację, czy została wpisana ręcznie."),
            ("Jak je pobieramy:",
             "automatycznie, przez oficjalne API wybranego dostawcy (np. Strava, COROS, Wahoo), "
             "dopiero po Twojej autoryzacji, regularnie (obecnie co godzinę). "
             "Pobieramy wyłącznie dane z Twojego konta."),
            ("Do czego służą i kto je widzi:",
             "do wyliczenia klubowego rankingu kilometrów. Ranking (Twoje imię i nazwisko "
             "oraz miesięczne sumy: liczba aktywności, dystans, czas) nie jest publiczny — "
             "widzą go wyłącznie wskazani administratorzy rankingu (organizatorzy). "
             "Nie sprzedajemy ani nie przekazujemy danych podmiotom trzecim, nie używamy ich "
             "do reklam ani do trenowania modeli AI."),
            ("Jak długo je przechowujemy:",
             "ze Stravy: szczegóły aktywności tylko przez 7 dni, potem zostają wyłącznie "
             "miesięczne sumy (liczba aktywności, dystans i czas jazdy rowerem) oraz Twoje imię, "
             "nazwisko i identyfikator. Pozostałe dane — do czasu wycofania zgody lub "
             "prośby o usunięcie. Po cofnięciu dostępu w Stravie usuwamy Twoje dane ze Stravy."),
            ("Jak wycofać zgodę:",
             "w każdej chwili — cofnij dostęp w ustawieniach swojego dostawcy "
             "(Strava: Settings → My Apps → Revoke Access) lub napisz do nas. "
             "Po cofnięciu dostępu przestajemy pobierać dane."),
            ("Jak zażądać usunięcia danych lub ich kopii:",
             "napisz na adres ze strony wsparcia. Usuniemy Twoje dane w ciągu 30 dni "
             "i potwierdzimy to wiadomością."),
        ],
        "more": "Szczegóły, kontakt i prywatność:",
        "support": "Wsparcie i prywatność",
        "check": ("Mam ukończone 18 lat. Zapoznałem(-am) się z powyższym i wyrażam zgodę na "
                  "przetwarzanie moich danych w opisany sposób, w tym na pokazywanie mojego "
                  "imienia i nazwiska oraz miesięcznych sum administratorom rankingu."),
        "connect": "Połącz z",
        "soon": "Wkrótce",
        "footer": "ranking klubowy",
        "other_lang": ("English", "/?lang=en"),
    },
    "en": {
        "html_lang": "en",
        "title": "Tour de Malborska — Connect your device",
        "tagline": "Connect your sports account to join the club's kilometre ranking.",
        "need_consent": "To continue, read the information below and tick the consent box.",
        "consent_title": "Before you connect",
        "consent_intro": "Please read how we process your data:",
        "items": [
            ("What we collect:",
             "your name (or nickname) from your account, sex (if provided), and for each "
             "activity: date, sport type, distance, moving time, name, and whether it was "
             "entered manually."),
            ("How we collect it:",
             "automatically, through the official API of the provider you choose (e.g. Strava, "
             "COROS, Wahoo), only after you authorize it, on a regular schedule (currently "
             "hourly). We only read data from your own account."),
            ("What it is used for and who sees it:",
             "to calculate the club's kilometre ranking. The ranking (your name and monthly "
             "totals: number of activities, distance, time) is not public — only the named "
             "ranking administrators (the organizers) can see it. "
             "We do not sell or share your data with third parties, and do not use it for "
             "advertising or to train AI models."),
            ("How long we keep it:",
             "from Strava: activity details for 7 days only, after which only monthly totals "
             "(number of activities, cycling distance and time) plus your name and ID remain. "
             "Other data: until you withdraw consent or ask for deletion. "
             "If you revoke access in Strava, we delete your Strava data."),
            ("How to withdraw consent:",
             "at any time — revoke access in your provider's settings "
             "(Strava: Settings → My Apps → Revoke Access) or write to us. "
             "Once access is revoked we stop collecting data."),
            ("How to request deletion or a copy of your data:",
             "write to the address on the support page. We will delete your data within "
             "30 days and confirm it by message."),
        ],
        "more": "Details, contact and privacy:",
        "support": "Support & privacy",
        "check": ("I am at least 18 years old. I have read the above and consent to my data "
                  "being processed as described, including showing my name and monthly totals "
                  "to the ranking administrators."),
        "connect": "Connect with",
        "soon": "Soon",
        "footer": "club ranking",
        "other_lang": ("Polski", "/?lang=pl"),
    },
}


def _button(label, color, path, status, t, slug=""):
    if status == "live" and path and slug == "strava":
        # Official "Connect with Strava" button, used UNMODIFIED as required by
        # Strava's Brand Guidelines (no recolouring, resizing artefacts, filters
        # or animation). Height 48px = the @1x size Strava specifies.
        from strava_button import STRAVA_BUTTON_DATA_URI, STRAVA_BUTTON_HEIGHT_PX
        return (
            f'<button class="btn-strava" type="submit" formaction="{path}" '
            f'aria-label="Connect with Strava">'
            f'<img src="{STRAVA_BUTTON_DATA_URI}" alt="Connect with Strava" '
            f'height="{STRAVA_BUTTON_HEIGHT_PX}"></button>'
        )
    if status == "live" and path:
        return (
            f'<button class="btn" type="submit" formaction="{path}" style="--brand:{color}">'
            f'<span class="btn-label">{t["connect"]} {label}</span>'
            f'<span class="btn-arrow" aria-hidden="true">&rarr;</span></button>'
        )
    return (
        f'<span class="btn btn--soon" style="--brand:{color}" aria-disabled="true">'
        f'<span class="btn-dot" style="--brand:{color}"></span>'
        f'<span class="btn-label">{label}</span>'
        f'<span class="btn-soon">{t["soon"]}</span></span>'
    )


def render_connect_page(lang: str = "pl", need_consent: bool = False) -> str:
    lang = "en" if lang == "en" else "pl"
    t = TEXT[lang]
    other_label, other_href = t["other_lang"]

    buttons = "\n        ".join(
        _button(l, c, p, s, t, slug) for (l, slug, p, c, s) in PROVIDERS
    )
    items = "\n".join(
        f"<li><strong>{b}</strong> {txt}</li>" for (b, txt) in t["items"]
    )
    notice = f'<div class="notice" role="alert">{t["need_consent"]}</div>' if need_consent else ""
    support_href = "/support?lang=en" if lang == "en" else "/support"

    page = """<!DOCTYPE html>
<html lang="__HTML_LANG__">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f44336">
  <title>__TITLE__</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --brand-red: #f44336; --brand-gold: #ffd740;
      --page: #fafafa; --card: #ffffff;
      --text: #212121; --muted: #6b6b6b; --ring: #e6e6e6;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body {
      min-height: 100svh;
      font-family: 'Roboto', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      color: var(--text); background: var(--page);
      display: flex; flex-direction: column; align-items: center;
      padding: 0 20px max(28px, env(safe-area-inset-bottom));
    }
    .topbar {
      width: 100%; background: var(--brand-red); border-bottom: 4px solid var(--brand-gold);
      padding: max(16px, env(safe-area-inset-top)) 20px 16px; display: flex; justify-content: center;
    }
    .topbar .org {
      max-width: 440px; width: 100%; color: #fff; text-align: center;
      font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 0.82rem;
      letter-spacing: 0.02em; text-transform: uppercase; opacity: 0.95;
    }
    .wrap { width: 100%; max-width: 440px; margin: 0 auto; }
    .brand { text-align: center; margin: 28px 0 22px; }
    .brand h1 { font-family: 'Montserrat', sans-serif; font-size: 1.6rem; font-weight: 800; letter-spacing: -0.01em; margin: 0 0 8px; }
    .brand h1 .accent { color: var(--brand-red); }
    .brand p { margin: 0; color: var(--muted); font-size: 0.95rem; line-height: 1.45; }
    .card { background: var(--card); border: 1px solid var(--ring); border-radius: 18px; padding: 18px; box-shadow: 0 6px 24px rgba(0,0,0,0.06); }
    .notice { background: #fff3f2; border: 1px solid #f5c2be; color: #8a1f17; border-radius: 10px; padding: 10px 12px; font-size: 0.85rem; line-height: 1.4; margin-bottom: 14px; }
    .consent h2 { font-family: 'Montserrat', sans-serif; font-size: 1rem; font-weight: 700; margin: 0 0 6px; }
    .consent p { margin: 0 0 6px; color: var(--muted); font-size: 0.85rem; line-height: 1.5; }
    .consent ul { margin: 8px 0 4px; padding-left: 18px; }
    .consent li { color: var(--muted); font-size: 0.84rem; line-height: 1.5; margin-bottom: 7px; }
    .consent li strong { color: var(--text); }
    .consent .more { font-size: 0.84rem; }
    .consent a { color: var(--brand-red); }
    .check { display: flex; gap: 10px; align-items: flex-start; margin: 14px 0 16px; padding: 12px; border: 1px solid var(--ring); border-radius: 12px; background: #fcfcfc; font-size: 0.86rem; line-height: 1.45; cursor: pointer; }
    .check input { width: 20px; height: 20px; margin: 2px 0 0; flex: 0 0 auto; accent-color: var(--brand-red); }
    .list { display: flex; flex-direction: column; gap: 12px; }
    .btn {
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      width: 100%; padding: 16px 18px; border-radius: 12px;
      border: none; background: var(--brand); color: #fff; text-decoration: none;
      font-family: 'Montserrat', sans-serif; font-size: 1.02rem; font-weight: 600; line-height: 1;
      min-height: 56px; transition: transform .06s ease, filter .15s ease;
      -webkit-tap-highlight-color: transparent;
    }
    button.btn { appearance: none; -webkit-appearance: none; cursor: pointer; text-align: left; }
    /* Official Strava button: leave the artwork untouched (no filter/hover effects). */
    .btn-strava { appearance: none; -webkit-appearance: none; background: none; border: 0; padding: 0; margin: 0; cursor: pointer; display: block; line-height: 0; width: fit-content; -webkit-tap-highlight-color: transparent; }
    .btn-strava img { display: block; height: 48px; width: auto; }
    .btn-strava:focus-visible { outline: 3px solid #212121; outline-offset: 3px; border-radius: 6px; }
    .btn:active { transform: scale(0.985); }
    .btn:hover { filter: brightness(1.08); }
    .btn-arrow { font-size: 1.15rem; opacity: 0.9; }
    .btn--soon { background: #fff; color: var(--muted); border: 1px solid var(--ring); cursor: default; }
    .btn--soon:hover { filter: none; }
    .btn--soon:active { transform: none; }
    .btn-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--brand); flex: 0 0 auto; }
    .btn--soon .btn-label { flex: 1 1 auto; }
    .btn-soon { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); border: 1px solid var(--ring); border-radius: 999px; padding: 4px 10px; }
    .footer { margin-top: 22px; text-align: center; color: var(--muted); font-size: 0.75rem; line-height: 1.8; }
    .footer a { color: var(--brand-red); text-decoration: none; }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="org">Szkoła przy Malborskiej</div>
  </header>

  <main class="wrap">
    <div class="brand">
      <h1>Tour de <span class="accent">Malborska</span></h1>
      <p>__TAGLINE__</p>
    </div>

    __NOTICE__
    <form class="card" method="get" action="/">
      <section class="consent" aria-labelledby="consent-h">
        <h2 id="consent-h">__CONSENT_TITLE__</h2>
        <p>__CONSENT_INTRO__</p>
        <ul>
__ITEMS__
        </ul>
        <p class="more">__MORE__ <a href="__SUPPORT_HREF__">__SUPPORT__</a></p>
      </section>

      <label class="check">
        <input type="checkbox" name="consent" value="1" required>
        <span>__CHECK__</span>
      </label>

      <div class="list">
        __BUTTONS__
      </div>
    </form>

    <div class="footer">
      Tour de Malborska &middot; __FOOTER__ &middot;
      <a href="__SUPPORT_HREF__">__SUPPORT__</a> &middot;
      <a href="__OTHER_HREF__">__OTHER_LABEL__</a><br>
      <a href="https://szkolaprzymalborskiej.pl/">szkolaprzymalborskiej.pl</a>
    </div>
  </main>
</body>
</html>"""

    replacements = {
        "__HTML_LANG__": t["html_lang"],
        "__TITLE__": t["title"],
        "__TAGLINE__": t["tagline"],
        "__NOTICE__": notice,
        "__CONSENT_TITLE__": t["consent_title"],
        "__CONSENT_INTRO__": t["consent_intro"],
        "__ITEMS__": items,
        "__MORE__": t["more"],
        "__SUPPORT_HREF__": support_href,
        "__SUPPORT__": t["support"],
        "__CHECK__": t["check"],
        "__BUTTONS__": buttons,
        "__FOOTER__": t["footer"],
        "__OTHER_HREF__": other_href,
        "__OTHER_LABEL__": other_label,
    }
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page
