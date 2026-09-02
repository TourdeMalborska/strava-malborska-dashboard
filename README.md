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

## Aktualny status

- [x] Utworzone repozytorium GitHub.
- [x] Skonfigurowane automatyczne wdrożenie z gałęzi `main` do Vercel.
- [x] Działająca aplikacja FastAPI na Vercel.
- [x] Publiczny endpoint zwracający `{"status": "running"}`.
- [ ] Konfiguracja domeny `tdm.szkolaprzymalborskiej.pl`.
- [ ] Implementacja regulaminu i rejestracji zgody.
- [ ] Implementacja Strava OAuth.
- [ ] Bezpieczny zapis tokenów.
- [ ] Implementacja codziennej synchronizacji o 00:01.
- [ ] Pobieranie wyłącznie aktywności z poprzedniego dnia.
- [ ] Zapis aktywności do Supabase bez duplikatów.
- [ ] Implementacja rankingu kilometrów.

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

Uruchom aplikację z katalogu głównego repozytorium:

```powershell
uvicorn api.index:app --reload
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
