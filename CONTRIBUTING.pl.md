# Pomóż rozwijać LINAK

[English](CONTRIBUTING.md) · **Polski**

Możesz zgłosić problem, zaproponować usprawnienie lub wskazać niejasną instrukcję. Nie musisz pisać kodu ani znać przyczyny problemu.

## Zgłoś błąd

Zacznij od dostępnych obserwacji:

1. Sprawdź [istniejące zgłoszenia](https://github.com/solarssk/ha-linak/issues) i [polską instrukcję diagnostyczną](docs/diagnostics.pl.md).
2. Wypełnij [polski formularz błędu](https://github.com/solarssk/ha-linak/issues/new?template=bug.pl.yml).
3. Opisz oczekiwany i rzeczywisty wynik. Podaj znane wersje, model panelu, przebieg zdarzenia oraz czy połączenie wróciło samo.

Brakujące informacje oznacz „nie wiem”. Brak logów nie blokuje zgłoszenia.

Opcjonalna [instrukcja przygotowania zgłoszenia z AI](docs/diagnostics.pl.md#przygotuj-zgłoszenie-z-pomocą-ai) pomaga ułożyć szkic. Usuń prywatne dane przed przekazaniem ich modelowi. Sprawdź wynik przed wklejeniem do formularza.

**Przed udostępnieniem** usuń ze zrzutów i logów nazwy urządzeń, adresy Bluetooth, lokalizacje i dane dostępowe. Podatności zgłaszaj [prywatnie](https://github.com/solarssk/ha-linak/security/advisories/new), nie przez publiczny formularz.

**Nie powtarzaj nieoczekiwanego ruchu tylko dla nagrania lub logu.** Opisz to, co już zaobserwowano.

## Zaproponuj zmianę

Otwórz [zgłoszenie](https://github.com/solarssk/ha-linak/issues/new) i opisz, co chcesz zrobić, co przeszkadza i jaki wynik byłby pomocny. Poprawki tłumaczeń i instrukcji też są wartościowym wkładem.

Test sprzętowy uzgodnij wcześniej z opiekunem projektu. Pierwsze testy ruchu wymagają obecności przy biurku i możliwości fizycznego zatrzymania. Testy oprogramowania nie potwierdzają bezpieczeństwa fizycznego.

## Zmień kod lub dokumentację

Procedury programistyczne są osobnym materiałem po angielsku:

- [Środowisko i pełna walidacja](CONTRIBUTING.md#development-environment)
- [Struktura dokumentacji](CONTRIBUTING.md#technical-documentation-structure)
- [Aktualizacje zależności](CONTRIBUTING.md#updating-dependencies)
- [Metadane i przekazanie PR](CONTRIBUTING.md#pr-metadata-and-handoff)

W systemie Linux x86_64 uruchom ograniczony fuzzing dekoderów protokołu poleceniem `python fuzz/fuzz_protocol.py --duration-seconds 30`. Atheris testuje czyste dekodery z syntetycznymi ramkami, bez Home Assistanta, Bluetooth, sieci i ruchu. Atheris 3.1.0 udostępnia obecnie koło dla Pythona 3.14 tylko dla Linux x86_64, więc standardowe środowisko programistyczne macOS pomija to opcjonalne narzędzie. Pełne zasady podpisywania oraz weryfikacji paczki opisuje [instrukcja integralności artefaktu wydania](docs/release-integrity.pl.md).

Lista pip `allow` Dependabota obejmuje tylko niezależne narzędzia z `requirements-tools.txt` i `requirements-build.txt`. Dodając narzędzie, zaktualizuj tę listę i grupę tooling. Pakiety zarządzane przez HA oraz świadomie wybrany resolver `uv` nie podlegają osobnym aktualizacjom.

Pliki wskazane przez `-r` lub `-c` muszą pozostać dostępne do pobrania, także wygenerowane wejścia komponentów, audytu i resolvera. Wykluczenie ścieżki przerywa parsowanie przed filtrowaniem pakietów. Wykluczone pozostaje tylko `.github/locks/**`; po zaakceptowaniu aktualizacji narzędzi wygeneruj locki ponownie. Testy polityki sprawdzają dostępność wejść i podział odpowiedzialności za pakiety.
