![LINAK](docs/assets/linak-logo.svg)

# LINAK w Home Assistant

Steruj biurkiem z regulacją wysokości i panelem LINAK **DPG1C** z Home Assistanta przez Bluetooth. Wybieraj wysokość w centymetrach, korzystaj z zapisanych pozycji i sprawdzaj ustawienia przypomnień.

🇬🇧 [English](README.md) · 🇵🇱 **Polski**

[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2026.11.0%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Marketplace](https://img.shields.io/badge/Marketplace-Custom-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/blog/2026/11/04/release-202611/#custom-repositories)
[![CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/solarssk/ha-linak/blob/main/LICENSE)

## 🪑 Obsługiwane urządzenia

| Seria | Model | Obsługa | Test sprzętowy |
| --- | --- | :---: | :---: |
| DPG | DPG1C | ✓ | ✓* |
| DPG | DPG1M | ? | – |
| DPG | DPG1B | ? | – |
| DPG | DPG1I | ? | – |
| DPI | DPI1C | ✗ | – |

**✓** dostępne lub sprawdzone · **?** zgodność niepotwierdzona · **✗** nieobsługiwane · **–** brak testu.

\* DPG1C sprawdzono na jednym panelu, w [opisanym zakresie testów](docs/hardware-results.md). Nie oznacza to pełnej weryfikacji każdej funkcji i wersji urządzenia.

**0.1.0 jest do użycia pod nadzorem na DPG1C.** Akceptacja sprzętowa nie jest zakończona:

- Dojazd w pełnym zakresie, dokładność zatrzymania i powtarzalny powrót do obsługi panelu pozostają niezweryfikowane.
- Długotrwała niezawodność Bluetooth pozostaje niezweryfikowana. Uruchomienie i odzyskanie połączenia mogą trwać długo albo się nie udać, także po włączeniu Utrzymuj połączenie.

Przed użyciem automatyzacji przeczytaj [opis wydania](CHANGELOG.md) i [pozostałe testy sprzętowe](docs/hardware-results.md#hardware-acceptance-matrix).

Sprawdź model na etykiecie panelu. [Instrukcja testowania kolejnego modelu](docs/device-support.md#test-another-panel) jest po angielsku.

## 🏠 Biurko na pulpicie

Dodaj **Wysokość** do standardowej karty Home Assistanta, aby widzieć aktualną pozycję biurka. Suwakiem wybierzesz wysokość do pracy, a przyciskami zapisanych pozycji przejdziesz między siedzeniem a staniem.

Integracja działa przez Bluetooth bezpośrednio na urządzeniu z Home Assistantem. Nie potrzebujesz aplikacji telefonu, Maca ani osobnego mostka.

## 📊 Encje w Home Assistant

### Czujniki

Sprawdzaj odczyty biurka:

- 📏 **Wysokość** (`sensor`): aktualna wysokość blatu w centymetrach
- 🔖 **Zapisana wysokość 1–4** (`sensor`): wysokości zapisane na panelu, z osobnym czujnikiem dla każdej dostępnej pozycji
- 🔔 **Aktywny profil przypomnień** (`sensor`): wybrany profil
- ⏱️ **Profil 1–3: czas siedzenia** i **czas stania** (`sensor`): czasy ustawione na panelu
- 🧭 **Operacja** (`sensor`): sprawdzaj przygotowanie, ruch, zatrzymywanie i wynik polecenia

Czasy przypomnień są ustawieniami, a nie licznikami spędzonego czasu. Przeglądanie zapisanej wysokości nie porusza biurkiem.

**Operacja** wraca do stanu „brak operacji” około 10 sekund po pokazaniu wyniku. Atrybut `last_result` zachowuje wynik dla automatyzacji. Czujnik opisuje wykonanie polecenia przez integrację; nie jest niezależnym potwierdzeniem fizycznego osiągnięcia wysokości.

### Sterowanie

Korzystaj ze sterowania na stronie urządzenia, pulpicie lub w automatyzacji:

- 🎚️ **Wysokość zadana** (`number`): wybierz wysokość suwakiem w centymetrach
- ⏹️ **Stop** (`button`): zatrzymaj bieżący ruch
- 🔖 **Pozycja 1–4** (`button`): przesuń biurko do pozycji zapisanej na panelu; czujniki **Zapisana wysokość 1–4** tylko pokazują jej wysokość

Suwak działa co 1 cm w zmierzonym zakresie. Aktualizuje się po zakończeniu jazdy, a **Wysokość** pokazuje ruch na bieżąco. Przed wybraniem kolejnego celu poczekaj na zakończenie ruchu albo naciśnij **Stop**. Polecenia nie trafiają do kolejki.

### Konfiguracja

- 🔔 **Profil przypomnień** (`select`): wybierz Wyłączone lub Profil 1/2/3, zachowując czasy
- 📏 **Preferowane jednostki panelu** (`select`): wybierz Metryczne lub Cale dla panelu, niezależnie od Home Assistanta
- ⏱️ **Profil 1: czas siedzenia** (`number`): opcjonalne pole 1–60 pełnych minut dla nieaktywnego profilu, domyślnie wyłączone
- ⏱️ **Profil 1: czas stania** i **Profil 2–3: czas siedzenia/stania** (`number`): opcjonalne pola 1–60 minut, domyślnie wyłączone
- ↩️ **Profil 1: ustaw standardowy czas** (`button`): opcjonalny, domyślnie wyłączony; ustaw tylko czas siedzenia na 55 minut, bez resetu fabrycznego
- 🔌 **Utrzymuj połączenie** (`switch`): celowo zwolnij połączenie Bluetooth i połącz się ponownie, gdy będzie potrzebne

**Utrzymuj połączenie** jest domyślnie wyłączone. Włącz tę encję w jej ustawieniach, aby pokazać przełącznik. Wyłączenie przełącznika wstrzymuje odczyty i ponowne łączenie, również po restarcie, do czasu jego włączenia. Podczas jazdy najpierw zatrzymuje biurko.

W **Preferowane jednostki panelu** wybierz **Metryczne** lub **Cale**. Nie zmienia to jednostek w Home Assistant. Opcja Metryczne nie pozwala wybrać między centymetrami a milimetrami.

Po zapisaniu panel może nadal pokazywać poprzednią jednostkę. Nie poruszaj biurkiem tylko po to, żeby odświeżyć wyświetlacz. [Jak zmienić jednostki panelu](docs/controls.md#choose-panel-units).

### Diagnostyka

Te encje pomagają sprawdzić połączenie lub kalibrację wysokości:

- 🔗 **Połączenie** (`binary_sensor`): czy biurko jest połączone, a odczyty dostępne
- 📐 **Korekta wysokości** (`sensor`): punkt odniesienia zapisany na panelu
- 📶 **Siła sygnału Bluetooth** (`sensor`): ostatni sygnał odebrany przez Home Assistanta
- 🛠️ **Backend Bluetooth** (`sensor`): czy połączenie korzysta z lokalnego adaptera, czy z proxy

Siła sygnału i backend są opcjonalne. Włączysz je w **Ustawienia → Urządzenia i usługi → Encje**, po pokazaniu wyłączonych encji LINAK.

## 📋 Czego potrzebujesz

Przed instalacją przygotuj:

- **Home Assistant 2026.11.0 lub nowszy**
- Panel **DPG1C** w zasięgu Bluetooth
- Lokalny adapter Bluetooth albo zgodne aktywne **proxy Bluetooth ESPHome** z obsługą parowania

## 🚀 Instalacja i połączenie

1. Otwórz **Ustawienia → Marketplace → Dodaj z linku**, połącz konto GitHub po wyświetleniu prośby i wpisz `https://github.com/solarssk/ha-linak`.
2. Zainstaluj **LINAK**. Pierwsza instalacja tej integracji z konfiguracją przez interfejs nie wymaga restartu. Aktualizacja już załadowanej integracji nadal go wymaga.
3. Wyłącz integrację IKEA Idasen Desk korzystającą z tego samego biurka. Jeśli jest połączona inna aplikacja biurka, rozłącz ją.
4. Włącz **parowanie Bluetooth** na panelu.
5. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację**, wyszukaj **LINAK** i wybierz biurko. Możesz też użyć jego karty wykrywania.
6. Przejdź przez ekrany konfiguracji, aby nazwać biurko, sprawdzić połączenie i ustawić zakres wysokości.

Wybierz **Tylko monitorowanie**, jeśli chcesz korzystać z czujników bez przygotowywania sterowania. Zmierzony zakres wysokości dodasz później przez **Konfiguruj**.

Poczekaj do **60 sekund** na połączenie, a po nieudanej próbie do kolejnych **10 sekund** na jego zwolnienie. W razie błędu wykonaj wskazówki z komunikatu i spróbuj ponownie. [Instalacja ręczna](.github/README.pl.md#installation).

Marketplace zastępuje HACS w HA 2026.11 i migruje istniejące instalacje. Dodaj ten projekt z linku; obecność w domyślnym katalogu i ikona przed instalacją nie są gwarantowane. Po instalacji widoki mogą używać dołączonych grafik. Zobacz [szczegóły brandingu](docs/hacs-presentation.md#name-and-catalog-icon).

**HA poniżej 2026.11.0 nie jest wspierany**, także przy instalacji ręcznej. Instalacja ręczna lub z domyślnej gałęzi może nie wymuszać tego minimum.

## ⚙️ Zmień ustawienia biurka

Otwórz **Ustawienia → Urządzenia i usługi → LINAK → Konfiguruj**, aby zmienić nazwę w HA, ustawić zmierzony zakres ruchu lub sprawdzić kalibrację wysokości.

Jeśli panel pokazuje błędną wysokość, zmierz odległość od podłogi do góry blatu. Wpisz ją w **Wysokość z miarki**, a następnie sprawdź i potwierdź korektę. Zapis korekty nie porusza biurkiem.

Wysokość wyświetla się w pełnych centymetrach; kalibracja zachowuje dokładność pomiaru. Edycja zapisanych pozycji nie jest dostępna.

Przypomnienia zmienisz w sekcji **Konfiguracja** na stronie urządzenia:

1. Przed edycją czasu wybierz **Wyłączone** lub inny profil.
2. W ustawieniach encji włącz potrzebne pole czasu siedzenia lub stania.
3. Wpisz **1–60 pełnych minut**. Zmieni się tylko ten czas; pozostałe czasy i ustawienia pozostaną bez zmian.

Wszystkie sześć pól i przycisk standardowego czasu są domyślnie wyłączone dla nowych encji. Istniejące nazwy i wybory włączenia pozostają bez zmian, a czujniki czasów nadal są włączone. **Profil 1: ustaw standardowy czas** ustawia tylko czas siedzenia na **55 minut**, bez resetu fabrycznego.

Zapis przypomnień wymaga aktywnego klienta, poprawnych odczytów i nieruchomego biurka; nie aktywuje go ani nie porusza. Wybór profili 1/2 wymaga jeszcze akceptacji sprzętowej. Na sprzęcie sprawdzono tylko 50/55 minut siedzenia w nieaktywnym profilu 1; pozostałe pola mają testy symulowane. Zakres pola jest zasadą integracji, nie zaleceniem medycznym ani limitem firmware. [Procedura przypomnień](docs/controls.md#edit-one-reminder-duration) opisuje odzyskanie po błędzie i odczyty poza zakresem.

Puste pamięci nie blokują konfiguracji. Niedostępna grupa pamięci lub przypomnień nie musi blokować wysokości. Po przekroczeniu czasu odczytu grupa czeka pięć minut na ponowienie; przyciski Pozycja wymagają poprawnego odczytu całej pamięci.

## 🛠️ Pomoc

Zacznij od **Połączenia** i komunikatu Home Assistanta. Instrukcja zgłoszeń opisuje zbieranie i anonimizację diagnostyki:

- [Konfiguracja i pierwszy test sterowania](docs/controls.md)
- [Zgłoszenie i logi po polsku](docs/diagnostics.md#zgłoszenie-i-logi-po-polsku)
- [Opcjonalna pomoc AI w opisaniu problemu](docs/diagnostics.md#przygotuj-zgłoszenie-z-pomocą-ai)
- [Zgłoś błąd](https://github.com/solarssk/ha-linak/issues/new?template=bug.pl.yml)

## 📚 Dokumentacja techniczna

Materiały dla osób testujących kolejne modele i rozwijających integrację, po angielsku:

- [Spis dokumentacji](docs/README.md)
- [Rodziny urządzeń i instrukcja dla testerów](docs/device-support.md)
- [Zakres testów sprzętowych i znane ograniczenia](docs/hardware-results.md)
- [Lista zmian](CHANGELOG.md) · [Plan rozwoju](docs/roadmap.md) · [Współpraca](CONTRIBUTING.md)

Niezależny projekt społecznościowy, niezwiązany z LINAK ani IKEA. Kod jest na licencji MIT; grafiki LINAK należą do ich właściciela. [Pochodzenie grafik](docs/branding.md).
