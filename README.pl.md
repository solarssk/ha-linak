![LINAK](docs/assets/linak-logo.svg)

# Biurka LINAK w Home Assistant

Steruj biurkiem z regulacją wysokości i panelem LINAK **DPG1C** z Home Assistanta przez Bluetooth. Wybieraj wysokość w centymetrach, korzystaj z zapisanych pozycji i sprawdzaj ustawienia przypomnień.

🇬🇧 [English](README.md) · 🇵🇱 **Polski**

[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2026.10.4%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/solarssk/ha-linak/blob/main/LICENSE)

## 📏 Co zobaczysz

- **Czytelny pomiar wysokości:** centymetry z uwzględnieniem punktu odniesienia zapisanego na panelu.
- **Twoje zapisane pozycje:** podgląd wysokości zapamiętanych na biurku.
- **Ustawienia przypomnień w jednym miejscu:** wybrany profil i ustawione odstępy czasu.

Czasy przypomnień są ustawieniami, a nie licznikiem spędzonego czasu. Inne modele paneli nie mają potwierdzonej zgodności. [Pełna lista encji i wyniki testów →](.github/README.pl.md)

## 🏠 Biurko jako część Twojego pulpitu

Dodaj **Wysokość** do standardowej karty Home Assistanta i sprawdzaj pozycję biurka bez otwierania osobnej aplikacji. Zmiany wykonane fizycznym panelem docierają przez Bluetooth.

Podejrzyj w jednym miejscu zapisane wysokości do siedzenia i stania. Czujniki pokazują pamięć panelu; ich przeglądanie nie rozpoczyna ruchu. Czujniki przypomnień pokazują ustawione profile panelu, a nie wysyłają powiadomień na telefon.

## 📊 Encje w Home Assistant

### Czujniki

- 📏 **Wysokość** jest głównym czujnikiem pomiarowym, w centymetrach.
- 🔖 **Zapisana wysokość 1–4** pokazuje do czterech pozycji pamięci, w centymetrach.
- 🔔 **Aktywny profil przypomnień** wskazuje wybrany profil.
- ⏱️ **Profil 1–3: czas siedzenia** i **czas stania** pokazują ustawione czasy, w minutach.

Wysokość, zapisane pozycje i profile są zwykłymi czujnikami biurka (`sensor`). Ustawienia panelu odświeżają się co **60 sekund**. Przy utracie połączenia odczyty stają się niedostępne; HA ponawia próby, gdy integracja jest załadowana.

### Diagnostyka

- 📐 **Korekta wysokości** (`sensor`, cm): punkt odniesienia zapisany na panelu.
- 🔗 **Połączenie** (`binary_sensor`): czy biurko ma gotowe połączenie i poprawne odczyty. Przy zerwaniu pokazuje stan rozłączony.
- 📶 **Siła sygnału Bluetooth** (`sensor`, dBm): ostatnia reklama odbierana przez HA, nie pomiar aktywnego łącza.
- 🛠️ **Backend Bluetooth** (`sensor`): np. lokalny BlueZ albo proxy ESPHome, bez nazwy adaptera.

RSSI i backend są domyślnie wyłączone. Możesz je włączyć w **Ustawienia → Urządzenia i usługi → Encje**, po pokazaniu wyłączonych encji LINAK. To włącza odczyt diagnostyczny w HA, bez zmiany ustawień biurka.

Nazwa i adres Bluetooth są w informacjach urządzenia. Pobierana diagnostyka pomija nazwę, MAC i identyfikatory adapterów. Diagnostyka pojawia się po pomyślnym dodaniu integracji; nie zastępuje komunikatów pierwszej konfiguracji.

### Sterowanie

- 🎚️ **Wysokość zadana** (`number`, cm): wybierz wysokość biurka suwakiem
- ⏹️ **Stop** (`button`): zatrzymaj bieżący ruch
- 🔖 **Przejdź do zapisanej pozycji 1–4** (`button`): jedź do pozycji zapisanej na panelu

Suwak pokazuje bieżącą wysokość biurka. Przesuń go do wybranej pozycji, a przyciskiem **Stop** zatrzymaj jazdę. Przyciski pamięci przenoszą biurko do pozycji zapisanych na panelu.

Podczas dodawania integracji podaj zakres wysokości swojego biurka. Zmienisz go później w **Ustawienia → Urządzenia i usługi → Biurka LINAK → Konfiguruj**. Jeśli aktualizujesz starszą instalację, uzupełnij zakres w tym samym miejscu. [Instrukcja i pierwszy test po angielsku](docs/controls.md).

Zmiana offsetu, zapisywanie pamięci i zmiana przypomnień pozostają w [planie ustawień](docs/settings-reference.md). Offset jest nadal wyłącznie odczytywany w diagnostyce.

## 📋 Czego potrzebujesz

- **Home Assistant 2026.10.4 lub nowszego**.
- Panelu **DPG1C** w zasięgu Bluetooth.
- Lokalnego adaptera Bluetooth albo zgodnego aktywnego **proxy Bluetooth ESPHome** z obsługą parowania.

Integracja działa bezpośrednio na urządzeniu z HA. Nie wymaga Maca ani osobnego mostka.

## 🚀 Instalacja i połączenie

1. W HACS dodaj `https://github.com/solarssk/ha-linak` jako własne repozytorium typu **Integracja / Integration**.
2. Pobierz **LINAK Desks**, a następnie uruchom ponownie Home Assistant.
3. Zamknij aplikacje telefonu połączone z biurkiem i wyłącz integrację Idasen używającą tego samego biurka.
4. Włącz **parowanie Bluetooth** na panelu.
5. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację**. Wyszukaj **Biurka LINAK**, a następnie wybierz swoje biurko. Możesz też użyć karty wykrytego urządzenia.

Konfiguracja łączy się, uwierzytelnia i odczytuje panel. Poczekaj do **60 sekund**, a po błędzie do kolejnych **10 sekund** na zwolnienie połączenia. Nieudana próba pokaże przyczynę i pozwoli spróbować ponownie.

Karta wykrywania pokazuje nazwę biurka i krótką końcówkę adresu, np. **Office desk (EEFF)**. Jeśli nazwy jeszcze nie ma, używa **LINAK (EEFF)**. Po połączeniu integracja może odczytać nazwę Bluetooth i uzupełnić nazwę urządzenia. Nazwy ustawionej przez Ciebie w HA nie nadpisuje.

Nie ma jeszcze wydania oznaczonego tagiem; HACS pobiera główną gałąź. [Instalacja ręczna i szczegółowy przewodnik →](.github/README.pl.md)

## 🛠️ Gdy coś nie działa

Sprawdź komunikat błędu i dziennik `ha_linak`. W zgłoszeniu podaj wersję HA i integracji, model panelu oraz informację, czy używasz lokalnego adaptera, czy proxy. Przed udostępnieniem logów usuń adresy Bluetooth i nazwy biurka.

[Konfiguracja i diagnostyka](docs/onboarding.md) · [Zgłoś błąd](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml)

## 🪑 Zgodność i rozwój

**DPG1C jest pierwszym obsługiwanym panelem.** Siedem rozszerzonych zapytań odczytu sprawdzono na jednym fizycznym panelu przez macOS CoreBluetooth. Konfigurację, czujniki, błędy parowania i odzyskiwanie połączenia testujemy też wewnątrz HA z symulowanym Bluetooth.

Na Malinie zaobserwowano odczyty i ponowne połączenia po ręcznym sparowaniu hosta. Nowe automatyczne pierwsze parowanie i proxy ESPHome wymagają jeszcze testów. Zielony badge CI potwierdza testy oprogramowania, nie działanie każdego biurka i adaptera. [Wyniki testów sprzętowych →](docs/hardware-results.md)

### Testy sterowania

Testy oprogramowania obejmują encje, obsługę połączenia, przerwanie ruchu i zamykanie integracji. Wyniki fizycznego ruchu i Stop na DPG1C nadal wymagają potwierdzenia. [Pierwszy test w HA po angielsku](docs/controls.md) opisuje próby i raportowanie; [osobne narzędzie badawcze](docs/movement-test.md) służy do eksperymentów protokołu poza HA.

## 📚 Więcej informacji

[Przewodnik użytkownika](.github/README.pl.md) · [Lista zmian](CHANGELOG.md) · [Plan rozwoju](docs/roadmap.md) · [Współpraca](CONTRIBUTING.md)

[Badania protokołu](docs/protocol.md) · [Badania Bluetooth](docs/bluetooth-research.md) · [Jakość i utrzymanie](docs/governance.md)

Dokumentacja techniczna jest po angielsku. Niezależny projekt społecznościowy, niezwiązany z LINAK ani IKEA. Kod jest na licencji MIT; grafiki LINAK należą do ich właściciela. [Pochodzenie grafik](docs/branding.md).
