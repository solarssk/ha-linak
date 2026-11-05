<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../docs/assets/linak-logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="../docs/assets/linak-logo-light.svg">
    <img src="../docs/assets/linak-logo-light.svg" alt="LINAK: We improve your life" width="360">
  </picture>
</p>

<h1 align="center">LINAK w Home Assistant</h1>

<p align="center">
  <strong>Twoje biurko LINAK w Home Assistant.<br>Aktualna wysokość w centymetrach, zapisane wysokości i przypomnienia.</strong><br>
  Działa bezpośrednio w Home Assistant. Pierwszy obsługiwany panel: <strong>DPG1C</strong>.
</p>

<p align="center">
  🇬🇧 <a href="README.md">English</a> &nbsp;·&nbsp; 🇵🇱 <strong>Polski</strong>
</p>

<p align="center">
  <a href="../hacs.json"><img src="https://img.shields.io/badge/Home%20Assistant-2026.11.0%2B-41BDF5?logo=homeassistant&amp;logoColor=white" alt="Home Assistant 2026.11.0 lub nowszy"></a>
  <a href="https://www.home-assistant.io/blog/2026/11/04/release-202611/#custom-repositories"><img src="https://img.shields.io/badge/Marketplace-Custom-41BDF5?logo=homeassistant&amp;logoColor=white" alt="Własne repozytorium Marketplace"></a>
</p>

<p align="center">
  <a href="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml"><img src="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://app.codecov.io/gh/solarssk/ha-linak"><img src="https://codecov.io/gh/solarssk/ha-linak/graph/badge.svg" alt="Codecov"></a>
  <a href="https://sonarcloud.io/summary/new_code?id=solarssk_ha-linak"><img src="https://sonarcloud.io/api/project_badges/measure?project=solarssk_ha-linak&amp;metric=alert_status" alt="Sonar quality gate"></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak"><img src="https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge" alt="OpenSSF Scorecard"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="Licencja kodu: MIT"></a>
</p>

<details>
<summary><strong>Spis treści</strong></summary>

- [🪑 Obsługiwane urządzenia](#supported-panels)
- [📊 Encje w Home Assistant](#entities)
- [📋 Wymagania](#requirements)
- [📦 Instalacja](#installation)
- [🔌 Konfiguracja](#configuration)
- [🏠 Na co dzień](#daily-use)
- [📚 Pomoc i dokumentacja](#help)
- [📄 Licencja](#license)

</details>

<a id="supported-panels"></a>

## 🪑 Obsługiwane urządzenia

| Seria | Model | Obsługa | Test sprzętowy |
| --- | --- | :---: | :---: |
| DPG | DPG1C | ✓ | ✓* |
| DPG | DPG1M | ? | – |
| DPG | DPG1B | ? | – |
| DPG | DPG1I | ? | – |
| DPI | DPI1C | ✗ | – |

**✓** dostępne lub sprawdzone · **?** zgodność niepotwierdzona · **✗** nieobsługiwane · **–** brak testu.

\* DPG1C sprawdzono na jednym panelu, w [opisanym zakresie testów](../docs/hardware-results.md). Nie oznacza to pełnej weryfikacji każdej funkcji i wersji urządzenia.

**Zakres 0.1.0:** natywne sterowanie i ustawienia DPG1C do użycia pod nadzorem, bez deklaracji zakończonej akceptacji sprzętowej. Dojazd w pełnym zakresie, dokładność zatrzymania, powtarzalny powrót do obsługi panelu i długotrwała niezawodność Bluetooth pozostają niezweryfikowane. Uruchomienie i odzyskanie połączenia mogą trwać długo albo się nie udać, także po włączeniu Utrzymuj połączenie. Przed użyciem automatyzacji przeczytaj [opis wydania](../CHANGELOG.md) i [dowody oraz pozostałe testy](../docs/hardware-results.md#hardware-acceptance-matrix).

Sprawdź model na etykiecie panelu. [Instrukcja testowania kolejnego modelu](../docs/device-support.md#test-another-panel) jest po angielsku.

<a id="entities"></a>

## 📊 Encje w Home Assistant

Na stronie urządzenia znajdziesz odczyty biurka, diagnostykę i sterowanie. Nazwy odpowiadają polskim etykietom w HA; nazwa urządzenia może je poprzedzać.

Typ encji to domena Home Assistanta, np. `sensor` albo `button`. Nagłówki niżej grupują encje według ich przeznaczenia; jednostki mają osobną kolumnę.

### Czujniki

<table>
  <thead>
    <tr><th scope="col">Typ encji</th><th scope="col">Nazwa w HA</th><th scope="col">Jednostka</th><th scope="col">Co pokazuje</th></tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="6"><code>sensor</code></td>
      <td>📏 <strong>Wysokość</strong></td>
      <td>cm</td>
      <td>Aktualną wysokość biurka, z korektą panelu</td>
    </tr>
    <tr>
      <td>🔖 <strong>Zapisana wysokość 1–4</strong></td>
      <td>cm</td>
      <td>Wysokości zapamiętane na panelu; do czterech encji</td>
    </tr>
    <tr>
      <td>🔔 <strong>Aktywny profil przypomnień</strong></td>
      <td>-</td>
      <td>Numer wybranego profilu</td>
    </tr>
    <tr>
      <td>⏱️ <strong>Profil 1–3: czas siedzenia</strong></td>
      <td>min</td>
      <td>Czas siedzenia ustawiony w każdym z trzech profili</td>
    </tr>
    <tr>
      <td>🚶 <strong>Profil 1–3: czas stania</strong></td>
      <td>min</td>
      <td>Czas stania ustawiony w każdym z trzech profili</td>
    </tr>
    <tr><td>🧭 <strong>Operacja</strong></td><td>-</td><td>Przebieg i wynik polecenia ruchu</td></tr>
  </tbody>
</table>

- **Wysokość** jest głównym czujnikiem pomiarowym.
- Zapisane pozycje i profile przypomnień są zwykłymi czujnikami biurka, bez kategorii Diagnostyka.
- Czasy przypomnień to ustawione wartości, nie licznik spędzonego czasu.
- Czujniki nie sterują ruchem ani nie zmieniają ustawień.

**Operacja** pokazuje przebieg i wynik polecenia, a po około 10 sekundach wraca do stanu „brak operacji”. Atrybut `last_result` zachowuje wynik dla automatyzacji. Czujnik opisuje wykonanie polecenia; nie jest niezależnym potwierdzeniem fizycznego osiągnięcia wysokości.

### Sterowanie

<table>
  <thead><tr><th scope="col">Typ encji</th><th scope="col">Nazwa w HA</th><th scope="col">Jednostka</th><th scope="col">Działanie</th></tr></thead>
  <tbody>
    <tr><td><code>number</code></td><td>🎯 <strong>Wysokość zadana</strong></td><td>cm</td><td>Wybierz suwakiem wysokość</td></tr>
    <tr><td rowspan="2"><code>button</code></td><td>⏹️ <strong>Stop</strong></td><td>-</td><td>Przerwij bieżący ruch</td></tr>
    <tr><td>🔖 <strong>Pozycja 1–4</strong></td><td>-</td><td>Przesuń biurko do pozycji zapisanej na panelu; puste pozycje są niedostępne. Czujniki zapisanej wysokości tylko pokazują jej wysokość</td></tr>
  </tbody>
</table>

Suwak wybiera wysokość co 1 cm, wewnątrz zmierzonego zakresu. Aktualizuje się po zakończeniu jazdy, a czujnik **Wysokość** pokazuje ruch na bieżąco. Przed wyborem kolejnego celu poczekaj na zakończenie ruchu albo naciśnij **Stop**. Polecenia nie trafiają do kolejki.

### Konfiguracja

| Typ encji | Nazwa w HA | Domyślnie | Działanie |
| --- | --- | --- | --- |
| `select` | 🔔 **Profil przypomnień** | Włączona | Wybierz Wyłączone lub Profil 1/2/3, bez zmiany czasów i ruchu biurka |
| `select` | 📏 **Preferowane jednostki panelu** | Włączona | Wybierz Metryczne lub Cale dla panelu, niezależnie od Home Assistanta |
| `number` | ⏱️ **Profil 1: czas siedzenia** | Encja wyłączona | Wpisz 1–60 pełnych minut dla nieaktywnego profilu 1, zachowując pozostałe pola |
| `number` | ⏱️ **Profil 1: czas stania**, **Profil 2–3: czas siedzenia/stania** | Encja wyłączona | Opcjonalne pola 1–60 minut dla nieaktywnego profilu, bez zmiany pozostałych pól |
| `button` | ↩️ **Profil 1: ustaw standardowy czas** | Encja wyłączona | Ustaw tylko czas siedzenia na 55 minut, bez resetu fabrycznego |
| `switch` | 🔌 **Utrzymuj połączenie** | Encja wyłączona | Wyłącz przełącznik, aby zwolnić połączenie Bluetooth, lub włącz, aby połączyć się ponownie |

Włącz encję **Utrzymuj połączenie** w jej ustawieniach, aby pokazać przełącznik. Gdy przełącznik jest wyłączony, integracja wstrzymuje odczyty i ponowne łączenie, również po restarcie. Wyłączenie podczas jazdy najpierw zatrzymuje biurko.

W **Preferowane jednostki panelu** wybierz **Metryczne** lub **Cale**. Nie zmienia to jednostek w Home Assistant. Opcja Metryczne nie pozwala wybrać między centymetrami a milimetrami.

Po zapisaniu panel może nadal pokazywać poprzednią jednostkę. Nie poruszaj biurkiem tylko po to, żeby odświeżyć wyświetlacz. [Jak zmienić jednostki panelu](../docs/controls.md#choose-panel-units).

Ustawienia znajdziesz w **Ustawienia → Urządzenia i usługi → LINAK → Konfiguruj**. Zmienisz tam nazwę w HA, zakres ruchu i kalibrację wysokości. W **Wysokość z miarki** wpisz aktualny pomiar od podłogi do góry blatu, a następnie sprawdź i potwierdź korektę. Zapis nie porusza biurkiem. [Instrukcja konfiguracji](../docs/controls.md).

Profil przypomnień można zmienić na Wyłączone lub Profil 1/2/3. Wybór zachowuje czasy i pozostałe ustawienia panelu, nie porusza biurkiem i nie aktywuje klienta. Zapis wymaga aktywnego klienta i poprawnego odczytu przypomnień. Profile 1/2 wymagają jeszcze akceptacji sprzętowej. Edycja zapisanych pozycji nadal nie jest dostępna.

W sekcji Konfiguracja na stronie urządzenia są pola czasu siedzenia i stania wszystkich trzech profili, w **1–60 pełnych minutach**. Wszystkie sześć pól i przycisk standardowego czasu są domyślnie wyłączone dla nowych encji; włącz tylko potrzebne. Istniejące nazwy i wybory włączenia lub wyłączenia pozostają bez zmian. Czujniki czasów tylko do odczytu nadal są domyślnie włączone. Przed zmianą czasu wybranego profilu wybierz Wyłączone lub inny profil. Każda edycja zachowuje pozostałe pięć czasów i wszystkie flagi, bez przeliczania par; istniejące wartości poza zakresem pozostają widoczne. **Profil 1: ustaw standardowy czas** ustawia tylko czas siedzenia na **55 minut**, bez resetu fabrycznego i przywracania kopii. Zakres jest zasadą integracji, nie limitem sterownika ani zaleceniem medycznym. Wszystkie sześć pól sprawdzono w symulacji; na sprzęcie potwierdzono tylko 50/55 minut siedzenia w nieaktywnym profilu 1. [Kontrakt edycji](../docs/settings-reference.md#edit-reminder-durations).

### Diagnostyka

<table>
  <thead><tr><th scope="col">Typ encji</th><th scope="col">Nazwa w HA</th><th scope="col">Domyślnie</th><th scope="col">Znaczenie</th></tr></thead>
  <tbody>
    <tr><td rowspan="3"><code>sensor</code></td><td>📐 <strong>Korekta wysokości</strong></td><td>Włączony</td><td>Punkt odniesienia zapisany na panelu, w cm</td></tr>
    <tr><td>📶 <strong>Siła sygnału Bluetooth</strong></td><td>Wyłączony</td><td>Ostatnia reklama odbierana przez HA, w dBm; nie RSSI aktywnego łącza</td></tr>
    <tr><td>🛠️ <strong>Backend Bluetooth</strong></td><td>Wyłączony</td><td>Kategoria aktywnego połączenia, np. BlueZ lub ESPHome</td></tr>
    <tr><td><code>binary_sensor</code></td><td>🔗 <strong>Połączenie</strong></td><td>Włączony</td><td>Gotowa sesja biurka; stan rozłączony po zerwaniu</td></tr>
  </tbody>
</table>

Opcjonalne encje znajdziesz w **Ustawienia → Urządzenia i usługi → Encje**, po pokazaniu wyłączonych encji LINAK. Nie są przełącznikami ustawień biurka. Nazwa i MAC są informacjami urządzenia, bez osobnych sensorów. Pobierany plik diagnostyczny pomija te identyfikatory. [Jak interpretować diagnostykę →](../docs/diagnostics.md)

<a id="requirements"></a>

## 📋 Wymagania

- **Home Assistant 2026.11.0+**.
- Wbudowany **Marketplace** do instalacji lub ręczne skopiowanie integracji.
- Adapter Bluetooth w zasięgu biurka lub zgodne **aktywne proxy Bluetooth ESPHome**.
- Wolne połączenie Bluetooth na panelu.

<a id="installation"></a>

## 📦 Instalacja

### Przez Marketplace

1. Otwórz **Ustawienia → Marketplace → Dodaj z linku / Add from link** i połącz konto GitHub po wyświetleniu prośby.
2. Wpisz `https://github.com/solarssk/ha-linak`.
3. Zainstaluj **LINAK**. Pierwsza instalacja z konfiguracją przez interfejs ładuje się bez restartu; aktualizacja już załadowanej integracji nadal go wymaga.

HA 2026.11 migruje dotychczasowe repozytoria i instalacje HACS do Marketplace. Ten projekt dodaje się z linku, bez deklaracji obecności w domyślnym katalogu. Po instalacji widoki używają dołączonych grafik; ikona w katalogu przed instalacją nie jest gwarantowana. Zobacz [kontrakt brandingu](../docs/hacs-presentation.md#name-and-catalog-icon).

<details>
<summary>Wolisz instalację ręczną?</summary>

Skopiuj [`custom_components/ha_linak`](../custom_components/ha_linak) do folderu `custom_components` w konfiguracji Home Assistanta i uruchom ponownie HA.

HA poniżej 2026.11.0 również tu nie jest wspierany. Minimum w `hacs.json` jest sprawdzane dla repozytoriów z wydaniami, a nie jako blokada podczas działania każdej instalacji ręcznej lub z domyślnej gałęzi.

</details>

<a id="configuration"></a>

## 🔌 Konfiguracja

W Home Assistant integracja nazywa się **LINAK**. Jej wewnętrzna domena pozostaje `ha_linak`.

1. Zamknij aplikację telefonu. Wyłącz integrację IKEA Idasen Desk, jeśli używa tego samego biurka. LINAK wykrywa włączony wpis IKEA dla tego samego biurka i wyjaśnia, jak rozwiązać konflikt, zachowując jego konfigurację.
2. Włącz **tryb parowania Bluetooth** na panelu.
3. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację** i wyszukaj **LINAK** lub skorzystaj z karty wykrytego urządzenia.
4. Wybierz tę integrację o domenie **`ha_linak`**, a następnie swoje biurko.

Kreator prowadzi przez nazwę w HA, połączenie, zmierzony zakres ruchu i sprawdzenie wysokości. Wybierz **Tylko monitorowanie**, jeśli potrzebujesz samych odczytów. Sterowanie dodasz później przez **Konfiguruj**.

Po zatwierdzeniu zobaczysz ekran postępu. Poczekaj do **60 sekund** na połączenie, a po błędzie do kolejnych **10 sekund** na jego zwolnienie. Wykonaj wskazówki z komunikatu i spróbuj ponownie. Jeśli z biurkiem jest połączona inna aplikacja, rozłącz ją.

<a id="daily-use"></a>

## 🏠 Na co dzień

- Znajdziesz czujniki w **Ustawienia → Urządzenia i usługi → LINAK**.
- Dodaj wysokość biurka do pulpitu za pomocą standardowej karty HA.
- Podejrzyj wysokości zapisane na panelu. Ich przeglądanie nie porusza biurkiem.
- Wysokość aktualizuje się przez Bluetooth, a odczyt pozycji i punktu odniesienia jest sprawdzany co **60 sekund**. Zapisane pozycje i przypomnienia odświeżają się co **5 minut**, po ponownym połączeniu lub zmianie punktu odniesienia.
- Po błędzie połączenia czujniki stają się niedostępne, a HA ponawia próby, gdy są załadowane.

<details>
<summary>Usuwanie integracji</summary>

Usuń jej wpis w Home Assistant, usuń folder `custom_components/ha_linak` i uruchom ponownie HA. Usunięcie integracji nie cofa kalibracji zapisanej w panelu.

</details>

<a id="validation"></a>
<a id="help"></a>

## 📚 Pomoc i dokumentacja

Instrukcje szczegółowe są po angielsku:

- **Konfiguracja:** [Ustawienia i pierwszy test sterowania](../docs/controls.md).
- **Problemy z połączeniem lub sterowaniem:** [Rozwiązywanie problemów](../docs/diagnostics.md).
- **Zgłoszenie błędu:** [Formularz zgłoszenia](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml). Podaj model panelu, wersję HA i sposób połączenia. Pobierz diagnostykę ze strony urządzenia; z dodatkowych logów usuń nazwy i adresy Bluetooth.

### Dla testerów i programistów

- [Spis dokumentacji technicznej](../docs/README.md)
- [Rodziny urządzeń i testowanie kolejnego modelu](../docs/device-support.md)
- [Zakres testów sprzętowych i znane ograniczenia](../docs/hardware-results.md)
- [Lista zmian](../CHANGELOG.md) · [Plan rozwoju](../docs/roadmap.md) · [Współpraca](../CONTRIBUTING.md)
- [Prywatne zgłaszanie podatności](../SECURITY.md)

<a id="license"></a>

## 📄 Licencja

Kod: [MIT](../LICENSE). Niezależny projekt społecznościowy, niezwiązany z LINAK ani IKEA.

Dostarczone oficjalne grafiki LINAK służą identyfikacji sprzętu. Nazwy i grafiki pozostają własnością odpowiednich właścicieli i są wyłączone z licencji kodu. Zobacz [pochodzenie grafik](../docs/branding.md) i [źródła protokołu](../docs/protocol.md).
