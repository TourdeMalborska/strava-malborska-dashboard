"""
Athlete-facing "connect your device" landing page.

Mobile-first. Page shell follows the organization branding of
szkolaprzymalborskiej.pl (light theme; red #f44336 primary with gold #ffd740
accent; Montserrat headings + Roboto body). Provider buttons keep each
provider's OWN official brand color.

Fonts load from Google Fonts (matching the org site). Everything else is inline
so the page needs no other external assets.

Live providers link to their /auth/<provider> route; providers not yet wired for
per-user OAuth are shown disabled as "Wkrótce" (coming soon).
"""

# (label, provider slug, auth path or None, brand color, status)
PROVIDERS = [
    ("Strava",           "strava", "/auth/strava", "#FC4C02", "live"),
    ("COROS",            "coros",  "/auth/coros",  "#000000", "live"),
    ("Garmin Connect",   "garmin", None,           "#007CC3", "soon"),
    ("Wahoo",            "wahoo",  None,           "#1E73BE", "soon"),
    ("Polar",            "polar",  None,           "#E4002B", "soon"),
    ("Hammerhead Karoo", "karoo",  None,           "#111827", "soon"),
    ("Suunto",           "suunto", None,           "#1A1A1A", "soon"),
]


def _button(label, color, path, status):
    if status == "live" and path:
        return (
            f'<a class="btn" href="{path}" style="--brand:{color}">'
            f'<span class="btn-label">Połącz z {label}</span>'
            f'<span class="btn-arrow" aria-hidden="true">&rarr;</span></a>'
        )
    return (
        f'<span class="btn btn--soon" style="--brand:{color}" aria-disabled="true">'
        f'<span class="btn-dot" style="--brand:{color}"></span>'
        f'<span class="btn-label">{label}</span>'
        f'<span class="btn-soon">Wkrótce</span></span>'
    )


def render_connect_page() -> str:
    buttons = "\n        ".join(
        _button(l, c, p, s) for (l, _slug, p, c, s) in PROVIDERS
    )
    return """<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f44336">
  <title>Tour de Malborska — Połącz urządzenie</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --brand-red: #f44336;
      --brand-red-dark: #c5362c;
      --brand-gold: #ffd740;
      --brand-purple: #673ab7;
      --page: #fafafa;
      --card: #ffffff;
      --text: #212121;
      --muted: #6b6b6b;
      --ring: #e6e6e6;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body {
      min-height: 100svh;
      font-family: 'Roboto', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      color: var(--text);
      background: var(--page);
      display: flex; flex-direction: column; align-items: center;
      padding: 0 20px max(28px, env(safe-area-inset-bottom));
    }
    .topbar {
      width: 100%;
      background: var(--brand-red);
      /* gold underline accent, echoing the school colors */
      border-bottom: 4px solid var(--brand-gold);
      padding: max(16px, env(safe-area-inset-top)) 20px 16px;
      display: flex; justify-content: center;
    }
    .topbar .org {
      max-width: 440px; width: 100%;
      color: #fff; text-align: center;
      font-family: 'Montserrat', sans-serif;
      font-weight: 700; font-size: 0.82rem; letter-spacing: 0.02em;
      text-transform: uppercase; opacity: 0.95;
    }
    .wrap { width: 100%; max-width: 440px; margin: 0 auto; }
    .brand { text-align: center; margin: 28px 0 22px; }
    .brand h1 {
      font-family: 'Montserrat', sans-serif;
      font-size: 1.6rem; font-weight: 800; letter-spacing: -0.01em;
      margin: 0 0 8px; color: var(--text);
    }
    .brand h1 .accent { color: var(--brand-red); }
    .brand p { margin: 0; color: var(--muted); font-size: 0.95rem; line-height: 1.45; }
    .card {
      background: var(--card); border: 1px solid var(--ring);
      border-radius: 18px; padding: 18px;
      box-shadow: 0 6px 24px rgba(0,0,0,0.06);
    }
    .list { display: flex; flex-direction: column; gap: 12px; }
    .btn {
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      width: 100%; padding: 16px 18px; border-radius: 12px;
      border: none; background: var(--brand); color: #fff;
      text-decoration: none; font-family: 'Montserrat', sans-serif;
      font-size: 1.02rem; font-weight: 600; line-height: 1;
      min-height: 56px; transition: transform .06s ease, filter .15s ease;
      -webkit-tap-highlight-color: transparent;
    }
    .btn:active { transform: scale(0.985); }
    .btn:hover { filter: brightness(1.08); }
    .btn-arrow { font-size: 1.15rem; opacity: 0.9; }
    .btn--soon {
      background: #fff; color: var(--muted);
      border: 1px solid var(--ring); cursor: default;
    }
    .btn--soon:hover { filter: none; }
    .btn--soon:active { transform: none; }
    .btn-dot {
      width: 10px; height: 10px; border-radius: 50%;
      background: var(--brand); flex: 0 0 auto;
    }
    .btn--soon .btn-label { flex: 1 1 auto; }
    .btn-soon {
      font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.06em; color: var(--muted);
      border: 1px solid var(--ring); border-radius: 999px; padding: 4px 10px;
    }
    .note {
      margin: 18px 4px 0; color: var(--muted);
      font-size: 0.8rem; line-height: 1.5; text-align: center;
    }
    .footer {
      margin-top: 22px; text-align: center; color: var(--muted); font-size: 0.75rem;
    }
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
      <p>Połącz swoje konto sportowe, aby dołączyć do klubowego rankingu kilometrów.</p>
    </div>

    <div class="card">
      <div class="list">
        __BUTTONS__
      </div>
      <p class="note">
        Łącząc konto, wyrażasz zgodę na pobieranie danych o Twoich aktywnościach
        (dystans, data, czas) wyłącznie na potrzeby rankingu.
      </p>
    </div>

    <div class="footer">
      Tour de Malborska &middot;
      <a href="https://szkolaprzymalborskiej.pl/">szkolaprzymalborskiej.pl</a>
    </div>
  </main>
</body>
</html>""".replace("__BUTTONS__", buttons)
