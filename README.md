# Tour de Malborska Strava Dashboard

Dashboard klubu Tour de Malborska, publikowany docelowo pod adresem `tdm.szkolaprzymalborskiej.pl`.

## Cel projektu

Celem aplikacji jest prezentowanie klubowego rankingu opartego na danych aktywności zawodników ze Stravy.

Zakres MVP obejmuje wyłącznie:

- klub,
- zawodnika,
- datę aktywności,
- dystans przejechany przez zawodnika,
- ranking kilometrów.

Projekt powinien pozostać możliwie prosty i nie powinien zawierać funkcji niewymaganych przez MVP.

## Główne założenia

### 1. Indywidualna zgoda zawodnika

Każdy zawodnik samodzielnie łączy swoje konto Strava z aplikacją za pomocą procesu Strava OAuth.

Przed aktywacją udziału zawodnik:

1. akceptuje regulamin aplikacji,
2. wyraża zgodę na przetwarzanie danych wymaganych do utworzenia rankingu,
3. udziela aplikacji wymaganych uprawnień w Strava OAuth.

Aplikacja nie powinna pobierać ani przetwarzać danych zawodnika, który nie ukończył procesu zgody.

### 2. Brak webhooków w MVP

MVP nie korzysta z webhooków Stravy.

Aktualizacja rankingu nie wymaga danych w czasie rzeczywistym. Dane będą pobierane w kontrolowanym procesie okresowej synchronizacji.

Webhooki mogą zostać ponownie rozważone w przyszłości tylko wtedy, gdy pojawi się potwierdzona potrzeba biznesowa dotycząca szybszych aktualizacji.

### 3. Synchronizacja raz dziennie

Synchronizacja jest uruchamiana raz dziennie o godzinie `00:01`.

Każde uruchomienie:

1. wybiera zawodników z aktywną zgodą i połączonym kontem Strava,
2. odświeża token dostępu, jeżeli jest to wymagane,
3. pobiera wyłącznie aktywności z poprzedniego dnia,
4. zapisuje lub aktualizuje dane aktywności w Supabase,
5. przelicza dane wykorzystywane przez ranking.

Synchronizacja powinna być idempotentna, czyli jej ponowne wykonanie nie może tworzyć duplikatów aktywności.

## Przepływ użytkownika

```text
Zawodnik
    |
    v
Akceptacja regulaminu i zgody
    |
    v
Połącz konto Strava
    |
    v
Strava OAuth
    |
    v
Zapis identyfikatora zawodnika i tokenów
    |
    v
Codzienna synchronizacja o 00:01
    |
    v
Supabase
    |
    v
Ranking Tour de Malborska
```

## Architektura MVP

```text
Strava API
    |
    | OAuth + okresowe pobieranie aktywności
    v
Python / FastAPI na Vercel
    |
    v
Supabase
    |
    v
Dashboard
    |
    v
tdm.szkolaprzymalborskiej.pl
```

### Komponenty

- **GitHub**: repozytorium kodu i historia zmian.
- **Vercel**: hosting aplikacji Python/FastAPI oraz automatyczne wdrożenia po `git push` do gałęzi `main`.
- **Supabase**: przechowywanie zawodników, zgód, tokenów i aktywności.
- **Strava API**: źródło danych po indywidualnej autoryzacji zawodnika.
- **Domena**: `tdm.szkolaprzymalborskiej.pl`.

## Dane przetwarzane w MVP

Dla zawodnika aplikacja może przechowywać dane wymagane do działania integracji i rankingu, w szczególności:

- identyfikator zawodnika Strava,
- dane wymagane do wyświetlenia zawodnika w rankingu,
- status i datę akceptacji regulaminu,
- status i datę udzielenia zgody,
- zakres udzielonych uprawnień OAuth,
- token dostępu,
- token odświeżający,
- datę wygaśnięcia tokenu.

Dla aktywności aplikacja przetwarza minimalny zestaw danych wymagany przez ranking:

- identyfikator aktywności Strava,
- identyfikator zawodnika,
- datę aktywności,
- dystans,
- typ aktywności, jeżeli jest wymagany do kwalifikacji aktywności do rankingu.

## Zasady bezpieczeństwa

- Sekrety i tokeny nie mogą być przechowywane w repozytorium GitHub.
- Lokalne sekrety powinny znajdować się w pliku `.env`, który jest wykluczony przez `.gitignore`.
- Sekrety środowiska produkcyjnego powinny być skonfigurowane jako Environment Variables w Vercel.
- Dostęp do tokenów i danych zawodników w Supabase powinien być ograniczony do komponentów, które rzeczywiście ich potrzebują.
- Aplikacja powinna umożliwiać wycofanie zgody i zaprzestanie kolejnych synchronizacji zawodnika.

## Zarządzanie sekretami (Infisical)

Sekrety są zarządzane centralnie w Infisical (projekt `tourdemalborska`, Cloud, region EU). Infisical jest jedynym źródłem prawdy, a wartości są **wypychane** (push/sync) do poszczególnych integracji. Dzięki temu aplikacja i workflow CI nadal odczytują zwykłe zmienne środowiskowe — kod nie wymaga żadnych zmian i nie zależy od Infisical w czasie działania.

### Układ w Infisical

- Projekt: `tourdemalborska`
- Środowiska: `dev`, `prod` (oraz dodatkowe, jeśli potrzebne)
- Foldery:
  - `/app` — sekrety aplikacji, synchronizowane do **Vercel**
  - `/backup` — sekrety workflow kopii zapasowej, synchronizowane do **GitHub Actions**

Pełny wykaz kluczy i miejsc ich użycia znajduje się w pliku [`SECRETS.md`](SECRETS.md). Szablon nazw zmiennych znajduje się w [`.env.example`](.env.example).

### Uruchomienie lokalne przez Infisical

Zalecane (bez lokalnego pliku `.env`):

```powershell
infisical run --env=dev --path=/app -- uvicorn api.index:app --reload
```

Jeśli konieczne jest wygenerowanie lokalnego `.env` (praca offline):

```powershell
infisical export --env=dev --path=/app --format=dotenv > .env
```

Plik `.env` pozostaje wykluczony przez `.gitignore`.

## Aktualny status

### Zrealizowane

- [x] Utworzone repozytorium GitHub.
- [x] Skonfigurowane automatyczne wdrożenie z gałęzi `main` do Vercel.
- [x] Działająca aplikacja FastAPI na Vercel.
- [x] Publiczny endpoint zwracający `{"status": "running"}`.
- [x] Implementacja Strava OAuth (`/auth/strava` + callback).
- [x] Bezpieczny zapis tokenów (centralnie w Infisical; w bazie w tabeli
      `athlete_providers` z włączonym RLS — tokeny nie są dostępne publicznie).
- [x] Implementacja codziennej synchronizacji o 00:01 (cron Vercel, chroniony
      `CRON_SECRET`).
- [x] Pobieranie wyłącznie aktywności z poprzedniego dnia.
- [x] Zapis aktywności do Supabase bez duplikatów (upsert po `activity_id`).
- [x] Model wieloproviderowy: kanoniczne `athlete_id`, tabela
      `athlete_providers`, pole `source` na aktywnościach (migracje 001/002).
- [x] Integracja COROS (MCP + OAuth 2.0 PKCE): rejestracja klienta, przepływ
      `/auth/coros`, synchronizacja aktywności ze źródłem `source='coros'`.
- [x] Kopie zapasowe Supabase do S3 (GitHub Actions) obejmujące
      `athlete_providers`.

### W toku / do zrobienia

- [ ] Konfiguracja domeny `tdm.szkolaprzymalborskiej.pl`.
- [ ] Implementacja regulaminu i rejestracji zgody.
- [ ] Implementacja rankingu kilometrów (widok/raport w Looker/Data Studio).
- [ ] `COROS_CLIENT_ID` w środowisku Vercel (wymagane do działania `/auth/coros`
      na produkcji).
- [ ] Weryfikacja end-to-end: realne połączenie konta COROS na produkcji i
      potwierdzenie aktywności `source='coros'` w rankingu.
- [ ] Migracja 003: usunięcie przestarzałych kolumn (`strava_athlete_id`,
      tokeny inline) — po potwierdzeniu, że widok raportowy ich nie używa.
- [ ] (Przy >20 użytkownikach COROS) rozważenie COROS Partner API zamiast MCP.

## Poza zakresem MVP

Na obecnym etapie poza zakresem pozostają:

- webhooki Stravy,
- synchronizacja w czasie rzeczywistym,
- pobieranie wszystkich danych profilu i wszystkich szczegółów aktywności,
- rozbudowane statystyki treningowe,
- funkcje społecznościowe,
- funkcje niewymagane do prezentacji podstawowego rankingu kilometrów.

## Uruchomienie lokalne

Zainstaluj zależności:

```powershell
pip install -r requirements.txt
```

Uruchom aplikację z katalogu głównego repozytorium, wstrzykując sekrety z
Infisical (brak lokalnego pliku `.env` — patrz `SECRETS.md`):

```powershell
infisical run --env=prod --path=/app -- uvicorn api.index:app --reload
```

Sprawdź endpoint:

```text
http://127.0.0.1:8000/
```

Oczekiwana odpowiedź:

```json
{
  "status": "running"
}
```

## Deployment

Zmiany wypchnięte do gałęzi `main` uruchamiają automatyczny build i deployment w Vercel.

```powershell
git add .
git commit -m "Opis zmiany"
git push
```

Po wykonaniu `git push` status deploymentu można sprawdzić w panelu projektu Vercel.
