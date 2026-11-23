"""
Support & privacy page (/support).

Strava API Policy requirements this page addresses:
  2.1  how to withdraw consent, how to request deletion, deletion confirmed
  2.2  end-user access to collected data on request
  2.3  easily accessible end-user support contact + clear links to the user's
       Strava account
  4.3  no implied affiliation/endorsement by Strava
  6.5  statement that Strava may collect Usage Data
  7.4  deletion within 30 days after revocation / request

The contact address comes from the SUPPORT_EMAIL environment variable. If it is
not set the page falls back to the school's website instead of showing a fake
address.

DRAFT NOTICE: this is operational information, not a lawyer-reviewed privacy
policy. The data controller (administrator) should be named and the text
reviewed before the app is opened beyond the current small group.

Languages: Polish (default) and English (?lang=en).
"""

import html

SCHOOL_URL = "https://szkolaprzymalborskiej.pl/"
STRAVA_APPS_URL = "https://www.strava.com/settings/apps"
STRAVA_PRIVACY_URL = "https://www.strava.com/legal/privacy"
UODO_URL = "https://uodo.gov.pl/"


def _contact_line(lang: str, email: str) -> str:
    if email:
        safe = html.escape(email, quote=True)
        mail = f'<a href="mailto:{safe}">{safe}</a>'
        if lang == "en":
            return (f"Questions, withdrawing consent, requesting deletion or a copy of your "
                    f"data: {mail}.")
        return (f"Pytania, wycofanie zgody, prośba o usunięcie danych lub ich kopię: {mail}.")
    school = f'<a href="{SCHOOL_URL}">szkolaprzymalborskiej.pl</a>'
    if lang == "en":
        return f"Contact the ranking organizers through the school website: {school}."
    return f"Skontaktuj się z organizatorem rankingu przez stronę szkoły: {school}."


def _sections(lang: str, email: str):
    contact = _contact_line(lang, email)
    if lang == "en":
        return [
            ("contact", "Contact",
             f"<p>{contact}</p>"
             "<p>The data controller is the organizer of the Tour de Malborska ranking "
             "(contact above).</p>"),
            ("disconnect", "How to disconnect your account",
             "<ul>"
             f'<li><strong>Strava:</strong> Settings → My Apps → Revoke Access '
             f'(<a href="{STRAVA_APPS_URL}">strava.com/settings/apps</a>).</li>'
             "<li><strong>Wahoo:</strong> in the Wahoo app: profile icon → Account → "
             "Authorized Apps.</li>"
             "<li><strong>COROS:</strong> write to us and we will disconnect your account.</li>"
             "<li><strong>Hammerhead Karoo:</strong> remove Tour de Malborska from the "
             "connected apps in your Hammerhead Dashboard, or write to us and we will "
             "disconnect your account.</li>"
             "</ul>"
             "<p>After access is revoked we stop collecting data from that account. For "
             "Strava your data is deleted automatically when Strava notifies us of the "
             "revocation (normally within minutes); for other providers it is deleted within "
             "30 days.</p>"),
            ("deletion", "Deleting your data / getting a copy",
             "<p>Write to the contact address with the subject “Delete my data” (or “Copy of my "
             "data”) and say which account it concerns. We will delete your data within 30 days "
             "and confirm it by message. A copy of the data we hold about you is provided on "
             "request.</p>"),
            ("privacy", "What data we store and who processes it",
             "<ul>"
             "<li><strong>From your sports account:</strong> name (or nickname), sex (if "
             "provided).</li>"
             "<li><strong>Per activity:</strong> date, sport type, distance, moving time, name, "
             "and whether it was entered manually.</li>"
             "<li><strong>Technical:</strong> the link between your account and the app, access "
             "tokens needed to fetch your data, and the date you gave consent.</li>"
             "</ul>"
             "<p><strong>Who sees it:</strong> the ranking (your name and monthly totals: "
             "number of activities, distance, time) is not public. Only the named ranking "
             "administrators can see it. We do not sell or share "
             "your data with third parties and do not use it for advertising, profiling or "
             "training AI models.</p>"
             "<p><strong>Processors:</strong> Supabase (database), Vercel (application hosting), "
             "Google Looker Studio (ranking display), Amazon Web Services S3 (database "
             "backups).</p>"
             "<p><strong>How long:</strong> <em>Strava:</em> activity details for 7 days only; "
             "after that only monthly totals (number of activities, cycling distance and "
             "time) plus your name and Strava ID remain, until you revoke access or ask for "
             "deletion. <em>Other providers:</em> until you withdraw consent or ask for "
             "deletion.</p>"),
            ("rights", "Your rights",
             "<p>You can ask for access to your data, correction, deletion, restriction, "
             "objection and portability, and withdraw your consent at any time (this does not "
             "affect earlier processing). You may complain to the supervisory authority — in "
             f'Poland the President of the Personal Data Protection Office '
             f'(<a href="{UODO_URL}">uodo.gov.pl</a>).</p>'),
            ("strava", "Strava data",
             "<p>Data from Strava is used only for the club ranking. Strava activity details "
             "are kept for at most 7 days. Strava may collect data "
             "about how this app uses its API (“Usage Data”) as described in the "
             f'<a href="{STRAVA_PRIVACY_URL}">Strava Privacy Policy</a>. This app is not '
             "affiliated with, endorsed or sponsored by Strava.</p>"),
        ]
    return [
        ("contact", "Kontakt",
         f"<p>{contact}</p>"
         "<p>Administratorem danych jest organizator rankingu Tour de Malborska "
         "(kontakt powyżej).</p>"),
        ("disconnect", "Jak odłączyć swoje konto",
         "<ul>"
         f'<li><strong>Strava:</strong> Settings → My Apps → Revoke Access '
         f'(<a href="{STRAVA_APPS_URL}">strava.com/settings/apps</a>).</li>'
         "<li><strong>Wahoo:</strong> w aplikacji Wahoo: ikona profilu → Konto → "
         "Authorized Apps.</li>"
         "<li><strong>COROS:</strong> napisz do nas — odłączymy Twoje konto.</li>"
         "<li><strong>Hammerhead Karoo:</strong> usuń Tour de Malborska z połączonych "
         "aplikacji w panelu Hammerhead Dashboard albo napisz do nas — odłączymy Twoje "
         "konto.</li>"
         "</ul>"
         "<p>Po cofnięciu dostępu przestajemy pobierać dane z tego konta. W przypadku Strava "
         "Twoje dane są usuwane automatycznie po otrzymaniu od Strava powiadomienia o "
         "cofnięciu dostępu (zwykle w ciągu kilku minut); u pozostałych dostawców — w ciągu "
         "30 dni.</p>"),
        ("deletion", "Usunięcie danych / kopia danych",
         "<p>Napisz na adres kontaktowy z tematem „Usuń moje dane” (lub „Kopia moich "
         "danych”) i wskaż, którego konta dotyczy prośba. Usuniemy Twoje dane w ciągu 30 dni "
         "i potwierdzimy to wiadomością. Kopię przechowywanych danych przekażemy na "
         "żądanie.</p>"),
        ("privacy", "Jakie dane przechowujemy i kto je przetwarza",
         "<ul>"
         "<li><strong>Z Twojego konta sportowego:</strong> imię i nazwisko (lub pseudonim), "
         "płeć (jeśli podana).</li>"
         "<li><strong>Dla każdej aktywności:</strong> data, rodzaj sportu, dystans, czas "
         "ruchu, nazwa oraz informacja, czy została wpisana ręcznie.</li>"
         "<li><strong>Techniczne:</strong> powiązanie Twojego konta z aplikacją, tokeny "
         "dostępu potrzebne do pobierania danych oraz data wyrażenia zgody.</li>"
         "</ul>"
         "<p><strong>Kto widzi dane:</strong> ranking (Twoje imię i nazwisko oraz miesięczne "
         "sumy: liczba aktywności, dystans, czas) nie jest publiczny. Widzą go wyłącznie "
         "wskazani administratorzy rankingu. Nie sprzedajemy "
         "ani nie udostępniamy danych podmiotom trzecim i nie używamy ich do reklam, "
         "profilowania ani do trenowania modeli AI.</p>"
         "<p><strong>Podmioty przetwarzające:</strong> Supabase (baza danych), Vercel "
         "(hosting aplikacji), Google Looker Studio (prezentacja rankingu), Amazon Web "
         "Services S3 (kopie zapasowe bazy).</p>"
         "<p><strong>Jak długo:</strong> <em>Strava:</em> szczegóły aktywności tylko przez 7 "
         "dni; potem zostają wyłącznie miesięczne sumy (liczba aktywności, dystans i czas "
         "jazdy rowerem) oraz Twoje imię, nazwisko i identyfikator Strava — do czasu "
         "cofnięcia dostępu lub prośby o usunięcie. <em>Pozostali dostawcy:</em> do czasu "
         "wycofania zgody lub prośby o usunięcie.</p>"),
        ("rights", "Twoje prawa",
         "<p>Możesz żądać dostępu do danych, ich sprostowania, usunięcia, ograniczenia "
         "przetwarzania, wnieść sprzeciw, przenieść dane oraz w każdej chwili wycofać zgodę "
         "(bez wpływu na zgodność z prawem wcześniejszego przetwarzania). Możesz złożyć "
         f'skargę do Prezesa Urzędu Ochrony Danych Osobowych (<a href="{UODO_URL}">uodo.gov.pl</a>).</p>'),
        ("strava", "Dane ze Strava",
         "<p>Dane ze Strava wykorzystujemy wyłącznie do rankingu klubowego. Szczegóły "
         "aktywności ze Strava przechowujemy najwyżej 7 dni. Strava może "
         "zbierać dane o korzystaniu z jej API przez aplikację („Usage Data”), zgodnie z "
         f'<a href="{STRAVA_PRIVACY_URL}">Polityką prywatności Strava</a>. Aplikacja nie jest '
         "powiązana ze Stravą, ani przez nią popierana lub sponsorowana.</p>"),
    ]


def render_support_page(lang: str = "pl", contact_email: str = None) -> str:
    lang = "en" if lang == "en" else "pl"
    sections = _sections(lang, contact_email)

    if lang == "en":
        title, lead = "Support & privacy", (
            "Tour de Malborska is a private, non-commercial kilometre ranking for the adult "
            "members of a primary school's cycling club. This page explains how to contact us, "
            "disconnect your account and have your data deleted.")
        back, other = "← Back to connecting accounts", ("Polski", "/support?lang=pl")
        home = "/?lang=en"
    else:
        title, lead = "Wsparcie i prywatność", (
            "Tour de Malborska to prywatny, niekomercyjny ranking kilometrów dla dorosłych "
            "uczestników klubu rowerowego szkoły. Ta strona wyjaśnia, jak się z nami "
            "skontaktować, odłączyć konto i usunąć dane.")
        back, other = "← Wróć do łączenia kont", ("English", "/support?lang=en")
        home = "/"

    body = "\n".join(
        f'<section id="{sid}"><h2>{stitle}</h2>{sbody}</section>'
        for (sid, stitle, sbody) in sections
    )

    page = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f44336">
  <title>__TITLE__ — Tour de Malborska</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body { min-height: 100svh; background: #fafafa; color: #212121;
      font-family: 'Roboto', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
      display: flex; flex-direction: column; align-items: center;
      padding: 0 20px max(28px, env(safe-area-inset-bottom)); }
    .topbar { width: 100%; background: #f44336; border-bottom: 4px solid #ffd740;
      padding: max(16px, env(safe-area-inset-top)) 20px 16px; display: flex; justify-content: center; }
    .topbar .org { max-width: 680px; width: 100%; color: #fff; text-align: center;
      font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 0.82rem;
      letter-spacing: 0.02em; text-transform: uppercase; opacity: 0.95; }
    main { width: 100%; max-width: 680px; margin: 0 auto; }
    h1 { font-family: 'Montserrat', sans-serif; font-size: 1.6rem; font-weight: 800; margin: 28px 0 8px; }
    .lead { color: #6b6b6b; font-size: 0.97rem; line-height: 1.55; margin: 0 0 18px; }
    section { background: #fff; border: 1px solid #e6e6e6; border-radius: 14px; padding: 16px 18px; margin-bottom: 14px; }
    h2 { font-family: 'Montserrat', sans-serif; font-size: 1.05rem; font-weight: 700; margin: 0 0 8px; }
    p, li { font-size: 0.92rem; line-height: 1.6; color: #3a3a3a; }
    p { margin: 0 0 8px; }
    ul { margin: 6px 0 8px; padding-left: 20px; }
    li { margin-bottom: 6px; }
    a { color: #c5362c; }
    .nav { display: flex; justify-content: space-between; gap: 12px; font-size: 0.85rem; margin: 6px 2px 0; }
  </style>
</head>
<body>
  <header class="topbar"><div class="org">Szkoła przy Malborskiej</div></header>
  <main>
    <h1>__TITLE__</h1>
    <p class="lead">__LEAD__</p>
__BODY__
    <div class="nav"><a href="__HOME__">__BACK__</a><a href="__OTHER_HREF__">__OTHER_LABEL__</a></div>
  </main>
</body>
</html>"""

    for key, value in {
        "__LANG__": lang, "__TITLE__": title, "__LEAD__": lead, "__BODY__": body,
        "__HOME__": home, "__BACK__": back,
        "__OTHER_HREF__": other[1], "__OTHER_LABEL__": other[0],
    }.items():
        page = page.replace(key, value)
    return page
