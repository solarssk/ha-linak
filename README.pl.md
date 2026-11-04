![LINAK](docs/assets/linak-logo.svg)

# LINAK w Home Assistant

Steruj biurkiem z regulacją wysokości i panelem LINAK **DPG1C** z Home Assistanta przez Bluetooth. Wybieraj wysokość w centymetrach, korzystaj z zapisanych pozycji i sprawdzaj ustawienia przypomnień.

🇬🇧 [English](README.md) · 🇵🇱 **Polski**

[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2026.10.4%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/solarssk/ha-linak/blob/main/LICENSE)

## 🪑 Obsługiwane urządzenia

- **Panel biurkowy DPG1C:** sterowanie wysokością przez Bluetooth, zapisane pozycje i odczyt przypomnień

Inne modele nie mają potwierdzonej zgodności. Przed instalacją sprawdź etykietę panelu. [Testowanie innego modelu](docs/device-support.md#test-another-panel) ma osobną instrukcję po angielsku.

## 🏠 Biurko na pulpicie

Dodaj **Wysokość** do standardowej karty Home Assistanta, aby widzieć aktualną pozycję biurka. Suwakiem wybierzesz wysokość do pracy, a przyciskami zapisanych pozycji przejdziesz między siedzeniem a staniem.

Integracja działa przez Bluetooth bezpośrednio na urządzeniu z Home Assistantem. Nie potrzebujesz aplikacji telefonu, Maca ani osobnego mostka.

## 📊 Encje w Home Assistant

### Czujniki

Sprawdzaj odczyty biurka:

- 📏 **Wysokość:** aktualna wysokość blatu w centymetrach
- 🔖 **Zapisana wysokość 1–4:** wysokości zapisane na panelu, z osobnym czujnikiem dla każdej dostępnej pozycji
- 🔔 **Aktywny profil przypomnień:** wybrany profil
- ⏱️ **Profil 1–3: czas siedzenia** i **czas stania:** czasy ustawione na panelu

Czasy przypomnień są ustawieniami, a nie licznikami spędzonego czasu. Przeglądanie zapisanej wysokości nie porusza biurkiem.

### Sterowanie

Korzystaj ze sterowania na stronie urządzenia, pulpicie lub w automatyzacji:

- 🎚️ **Wysokość zadana:** wybierz wysokość suwakiem w centymetrach
- ⏹️ **Stop:** zatrzymaj bieżący ruch
- 🔖 **Przejdź do zapisanej pozycji 1–4:** przesuń biurko do pozycji zapisanej na panelu
- 🧭 **Operacja:** sprawdzaj przygotowanie, ruch, zatrzymywanie i wynik polecenia

Suwak działa co 1 cm w zmierzonym zakresie. Aktualizuje się po zakończeniu jazdy, a **Wysokość** pokazuje ruch na bieżąco. Przed wybraniem kolejnego celu poczekaj na zakończenie ruchu albo naciśnij **Stop**. Polecenia nie trafiają do kolejki.

**Operacja** wraca do stanu „brak operacji” około 10 sekund po pokazaniu wyniku. Atrybut `last_result` zachowuje wynik dla automatyzacji. Czujnik opisuje wykonanie polecenia przez integrację; nie jest niezależnym potwierdzeniem fizycznego osiągnięcia wysokości.

### Połączenie i diagnostyka

Te encje pomagają sprawdzić połączenie lub kalibrację wysokości:

- 🔗 **Połączenie:** czy biurko jest połączone, a odczyty dostępne
- 📐 **Korekta wysokości:** punkt odniesienia zapisany na panelu
- 📶 **Siła sygnału Bluetooth:** ostatni sygnał odebrany przez Home Assistanta
- 🛠️ **Backend Bluetooth:** czy połączenie korzysta z lokalnego adaptera, czy z proxy
- 🔌 **Utrzymuj połączenie:** celowo zwolnij połączenie Bluetooth i połącz się ponownie, gdy będzie potrzebne

Siła sygnału, backend i Utrzymuj połączenie są opcjonalne. Włączysz je w **Ustawienia → Urządzenia i usługi → Encje**, po pokazaniu wyłączonych encji LINAK. Wyłączenie przełącznika **Utrzymuj połączenie** wstrzymuje odczyty i ponowne łączenie, również po restarcie, do czasu jego włączenia. Podczas jazdy najpierw zatrzymuje biurko.

## 📋 Czego potrzebujesz

Przed instalacją przygotuj:

- **Home Assistant 2026.10.4 lub nowszy**
- Panel **DPG1C** w zasięgu Bluetooth
- Lokalny adapter Bluetooth albo zgodne aktywne **proxy Bluetooth ESPHome** z obsługą parowania

## 🚀 Instalacja i połączenie

1. W HACS dodaj `https://github.com/solarssk/ha-linak` jako własne repozytorium typu **Integracja / Integration**.
2. Pobierz **LINAK**, a następnie uruchom ponownie Home Assistant.
3. Wyłącz integrację IKEA Idasen Desk korzystającą z tego samego biurka. Jeśli jest połączona inna aplikacja biurka, rozłącz ją.
4. Włącz **parowanie Bluetooth** na panelu.
5. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację**, wyszukaj **LINAK** i wybierz biurko. Możesz też użyć jego karty wykrywania.
6. Przejdź przez ekrany konfiguracji, aby nazwać biurko, sprawdzić połączenie i ustawić zakres wysokości.

Wybierz **Tylko monitorowanie**, jeśli chcesz korzystać z czujników bez przygotowywania sterowania. Zmierzony zakres wysokości dodasz później przez **Konfiguruj**.

Poczekaj do **60 sekund** na połączenie, a po nieudanej próbie do kolejnych **10 sekund** na jego zwolnienie. W razie błędu wykonaj wskazówki z komunikatu i spróbuj ponownie. [Instalacja ręczna](.github/README.pl.md#installation).

## ⚙️ Zmień ustawienia biurka

Otwórz **Ustawienia → Urządzenia i usługi → LINAK → Konfiguruj**, aby zmienić nazwę w HA, ustawić zmierzony zakres ruchu lub sprawdzić kalibrację wysokości.

Jeśli panel pokazuje błędną wysokość, zmierz odległość od podłogi do góry blatu. Wpisz ją w **Wysokość z miarki**, a następnie sprawdź i potwierdź korektę. Zapis korekty nie porusza biurkiem.

Wysokość wyświetla się w pełnych centymetrach. Pomiary wpisuj z dokładnością miarki; kalibracja zachowuje tę dokładność. Integracja odczytuje zapisane pozycje i przypomnienia, ale jeszcze ich nie edytuje.

## 🛠️ Pomoc

Jeśli odczyty staną się niedostępne, sprawdź **Połączenie** i komunikat Home Assistanta. Na stronie urządzenia LINAK pobierzesz diagnostykę. W zgłoszeniu błędu podaj model panelu, wersje HA i integracji oraz informację, czy używasz lokalnego adaptera, czy proxy. Z dołączanych logów usuń prywatne nazwy i adresy Bluetooth.

Instrukcje szczegółowe są po angielsku:

- [Konfiguracja i pierwszy test sterowania](docs/controls.md)
- [Rozwiązywanie problemów](docs/diagnostics.md)
- [Zgłoś błąd](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml)

## 📚 Dokumentacja techniczna

Materiały dla osób testujących kolejne modele i rozwijających integrację, po angielsku:

- [Spis dokumentacji](docs/README.md)
- [Rodziny urządzeń i instrukcja dla testerów](docs/device-support.md)
- [Zakres testów sprzętowych i znane ograniczenia](docs/hardware-results.md)
- [Lista zmian](CHANGELOG.md) · [Plan rozwoju](docs/roadmap.md) · [Współpraca](CONTRIBUTING.md)

Niezależny projekt społecznościowy, niezwiązany z LINAK ani IKEA. Kod jest na licencji MIT; grafiki LINAK należą do ich właściciela. [Pochodzenie grafik](docs/branding.md).
