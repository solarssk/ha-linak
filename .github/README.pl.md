<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../docs/assets/linak-logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="../docs/assets/linak-logo-light.svg">
    <img src="../docs/assets/linak-logo-light.svg" alt="LINAK — We improve your life" width="360">
  </picture>
</p>

<h1 align="center">LINAK dla Home Assistant</h1>

<p align="center">
  <strong>Twoje biurko LINAK w Home Assistant.<br>Aktualna wysokość w centymetrach, zapisane wysokości i przypomnienia.</strong><br>
  Działa bezpośrednio w Home Assistant. Pierwszy obsługiwany panel: <strong>DPG1C</strong>.
</p>

<p align="center">
  🇬🇧 <a href="README.md">English</a> &nbsp;·&nbsp; 🇵🇱 <strong>Polski</strong>
</p>

<p align="center">
  <a href="../hacs.json"><img src="https://img.shields.io/badge/Home%20Assistant-2026.10.4%2B-41BDF5?logo=homeassistant&amp;logoColor=white" alt="Home Assistant 2026.10.4 lub nowszy"></a>
  <a href="https://www.hacs.xyz/docs/faq/custom_repositories/"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&amp;logoColor=white" alt="Własne repozytorium HACS"></a>
</p>

<p align="center">
  <a href="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml"><img src="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://app.codecov.io/gh/solarssk/ha-linak"><img src="https://codecov.io/gh/solarssk/ha-linak/graph/badge.svg" alt="Codecov"></a>
  <a href="https://sonarcloud.io/summary/new_code?id=solarssk_ha-linak"><img src="https://sonarcloud.io/api/project_badges/measure?project=solarssk_ha-linak&amp;metric=alert_status" alt="Sonar quality gate"></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak"><img src="https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge" alt="OpenSSF Scorecard"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="Licencja kodu: MIT"></a>
</p>

> [!IMPORTANT]
> **Wersja alfa, tylko odczyt.** Możesz przeglądać dane biurka. Sterowanie ruchem, Stop i zmiana ustawień panelu w HA są jeszcze w przygotowaniu. [Co dalej? →](../docs/roadmap.md)

<details>
<summary><strong>Spis treści</strong></summary>

- [🪑 Obsługiwane panele](#supported-panels)
- [📊 Encje w Home Assistant](#entities)
- [📋 Wymagania](#requirements)
- [📦 Instalacja](#installation)
- [🔌 Konfiguracja](#configuration)
- [🏠 Na co dzień](#daily-use)
- [🧪 Stan testów](#validation)
- [🕹️ Stan prac nad sterowaniem](#controls)
- [📚 Pomoc i dokumentacja](#help)
- [📄 Licencja](#license)

</details>

<a id="supported-panels"></a>

## 🪑 Obsługiwane panele

Pierwszym obsługiwanym modelem jest **DPG1C**. Zakres tej wersji obejmuje odczyt danych.

| Panel LINAK | Dostępne funkcje | Potwierdzenie na sprzęcie |
| --- | --- | --- |
| **DPG1C** | Wysokość, zapisane wysokości, korekta wysokości i profile przypomnień | Zapytania odczytu sprawdzone na jednym panelu |

Inne modele paneli nie mają jeszcze potwierdzonej zgodności. [Wyniki odczytów →](../docs/hardware-results.md)

<a id="entities"></a>

## 📊 Encje w Home Assistant

Integracja tworzy **encje czujników (`sensor`) i diagnostyczny czujnik binarny (`binary_sensor`)**. Nazwy poniżej odpowiadają polskim etykietom w HA; nazwa urządzenia może je poprzedzać.

<table>
  <thead>
    <tr><th scope="col">Typ encji</th><th scope="col">Nazwa w HA</th><th scope="col">Jednostka</th><th scope="col">Co pokazuje</th></tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="5">Czujnik<br><code>sensor</code></td>
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
      <td>—</td>
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
  </tbody>
</table>

- **Wysokość** jest głównym czujnikiem pomiarowym.
- Zapisane pozycje i profile przypomnień są zwykłymi czujnikami biurka, bez kategorii Diagnostyka.
- Czasy przypomnień to ustawione wartości, nie licznik spędzonego czasu.
- Czujniki nie sterują ruchem ani nie zmieniają ustawień.

### Diagnostyka

<table>
  <thead><tr><th scope="col">Typ encji</th><th scope="col">Nazwa w HA</th><th scope="col">Domyślnie</th><th scope="col">Znaczenie</th></tr></thead>
  <tbody>
    <tr><td rowspan="3">Czujnik<br><code>sensor</code></td><td>📐 <strong>Korekta wysokości</strong></td><td>Włączony</td><td>Punkt odniesienia zapisany na panelu, w cm</td></tr>
    <tr><td>📶 <strong>Siła sygnału Bluetooth</strong></td><td>Wyłączony</td><td>Ostatnia reklama odbierana przez HA, w dBm; nie RSSI aktywnego łącza</td></tr>
    <tr><td>🛠️ <strong>Backend Bluetooth</strong></td><td>Wyłączony</td><td>Kategoria aktywnego połączenia, np. BlueZ lub ESPHome</td></tr>
    <tr><td>Czujnik binarny<br><code>binary_sensor</code></td><td>🔗 <strong>Połączenie</strong></td><td>Włączony</td><td>Gotowa sesja biurka; stan rozłączony po zerwaniu</td></tr>
  </tbody>
</table>

Opcjonalne encje włączysz w **Ustawienia → Urządzenia i usługi → Encje**, po pokazaniu wyłączonych encji LINAK. Nie są przełącznikami ustawień biurka. Nazwa i MAC są informacjami urządzenia, bez osobnych sensorów. Pobierany plik diagnostyczny pomija te identyfikatory. [Jak interpretować diagnostykę →](../docs/diagnostics.md)

<a id="requirements"></a>

## 📋 Wymagania

- **Home Assistant 2026.10.4+**.
- **HACS** do instalacji lub ręczne skopiowanie integracji.
- Adapter Bluetooth w zasięgu biurka lub zgodne **aktywne proxy Bluetooth ESPHome**.
- Wolne połączenie Bluetooth na panelu.

Stan testów na Malinie i przez proxy opisujemy [osobno](#validation).

<a id="installation"></a>

## 📦 Instalacja

### Przez HACS

1. Otwórz HACS → **Własne repozytoria / Custom repositories**.
2. Dodaj ten adres i wybierz **Integracja / Integration**:

   ```text
   https://github.com/solarssk/ha-linak
   ```

3. Pobierz **LINAK** i uruchom ponownie Home Assistant.

<details>
<summary>Wolisz instalację ręczną?</summary>

Skopiuj [`custom_components/ha_linak`](../custom_components/ha_linak) do folderu `custom_components` w konfiguracji Home Assistanta i uruchom ponownie HA.

</details>

<a id="configuration"></a>

## 🔌 Konfiguracja

Karta wykrytego biurka pokazuje **LINAK · nazwę biurka**. Wewnętrzna domena integracji pozostaje `ha_linak`.

1. Zamknij aplikację telefonu. Wyłącz integrację IKEA Idasen Desk, jeśli używa tego samego biurka.
2. Włącz **tryb parowania Bluetooth** na panelu.
3. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację** i wyszukaj **LINAK** lub skorzystaj z karty wykrytego urządzenia.
4. Wybierz tę integrację o domenie **`ha_linak`**, a następnie swoje biurko.

Karta wykrywania używa nazwy biurka i krótkiej końcówki adresu, np. **Office desk (EEFF)**, zamiast powtórzonego LINAK. Gdy nazwa nie jest jeszcze dostępna, pokazuje **LINAK (EEFF)**. Po połączeniu może uzupełnić nazwę urządzenia z odczytu Bluetooth; nazwa urządzenia nadana przez Ciebie w HA ma pierwszeństwo.

Wersja **0.1.0a4** dodaje tymczasowego agenta parowania lokalnego BlueZ. Konfiguracja rozróżnia niedostępność lokalnego parowania, odrzucone uwierzytelnienie, brak obsługi parowania w proxy i zerwanie połączenia. Automatyczne pierwsze parowanie wymaga jeszcze testu na sprzęcie.

Po zatwierdzeniu zobaczysz ekran postępu HA. Próba ma limit **60 sekund**, a zwolnienie połączenia może potrwać kolejne **10 sekund**. Błąd pokazuje przyczynę i pozwala ponowić próbę. [Pierwsza konfiguracja i diagnostyka →](../docs/onboarding.md)

> [!TIP]
> Panel przyjmuje jedno połączenie Bluetooth naraz. Jeśli konfiguracja się nie udaje, sprawdź, czy nie jest połączona inna aplikacja. Lokalne parowanie odbywa się podczas konfiguracji; problem z usługą Bluetooth lub uprawnieniami D-Bus ma osobny komunikat.

<details>
<summary>O wersji alfa i wbudowanym wpisie LINAK</summary>

- To własne repozytorium HACS, poza domyślnym katalogiem.
- Nie ma jeszcze wersjonowanego wydania; HACS pobiera główną gałąź. Sprawdź [stan CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml).
- Wbudowany wpis LINAK prowadzi do innej integracji, IKEA Idasen Desk. Dla tego projektu wybierz `ha_linak`.

</details>

<a id="daily-use"></a>

## 🏠 Na co dzień

- Znajdziesz czujniki w **Ustawienia → Urządzenia i usługi → LINAK**.
- Dodaj wysokość biurka do pulpitu za pomocą standardowej karty HA.
- Podejrzyj wysokości zapisane na panelu. Ich przeglądanie nie porusza biurkiem.
- Wysokość aktualizuje się przez Bluetooth. Ustawienia odświeżają się co **60 sekund**.
- Po błędzie połączenia czujniki stają się niedostępne, a HA ponawia próby, gdy są załadowane.

<details>
<summary>Usuwanie integracji</summary>

Usuń jej wpis w Home Assistant, usuń folder `custom_components/ha_linak` i uruchom ponownie HA. Ta wersja nie zmienia ustawień zapisanych na panelu.

</details>

<a id="validation"></a>

## 🧪 Stan testów

- **Fizyczny DPG1C:** siedem zapytań odczytu sprawdzonych przez macOS CoreBluetooth.
- **Home Assistant 2026.10.4 z symulowanym Bluetooth:** testy konfiguracji, czujników, utraty i odzyskania połączenia oraz wyładowania integracji.
- **Malina:** zaobserwowano odczyty i ponowne połączenie po ręcznym parowaniu; automatyczne pierwsze parowanie wymaga jeszcze testu.
- **Proxy ESPHome:** test sprzętowy do wykonania.

To stan weryfikacji środowisk, nie lista modeli paneli. [Pełne wyniki →](../docs/hardware-results.md)

<details>
<summary>Ograniczenia pomiarów i sterowania</summary>

- Nieznane pola prędkości i liczniki nie są udostępniane jako potwierdzone pomiary.
- Wysokość biurka nie oznacza wykrywania obecności.
- Ruch i Stop pozostają niedostępne w HA. Nie ma encji rolety pokazującej wysokość w procentach.

</details>

<a id="controls"></a>

## 🕹️ Stan prac nad sterowaniem

| Funkcja | Dostępność teraz | Jak sprawdzić |
| --- | --- | --- |
| Odczyt wysokości, pamięci i przypomnień | W integracji HA | Dodaj LINAK przez HACS |
| Krótki ruch do celu i Stop po zadanym czasie | Osobne narzędzie badawcze do testu pod nadzorem; wyniki sprzętowe jeszcze niepotwierdzone | [Instrukcja testu po angielsku](../docs/movement-test.md) |
| Zadawanie wysokości, przycisk Stop i przyciski zapisanych pozycji w HA | Encje nie są jeszcze włączone | Po zapisaniu wyników sprzętowych i sprawdzeniu obsługi połączenia oraz cyklu pracy HA |
| Zmiana offsetu, pamięci lub przypomnień | Jeszcze niezaimplementowana | [Plan ustawień i kalibracji po angielsku](../docs/settings-reference.md) |

Narzędzie badawcze uruchamia się osobno na komputerze z Bluetooth obok biurka, po wyłączeniu innych klientów biurka. Wymaga zmierzonych granic, jawnego potwierdzenia ruchu i celu oddalonego najwyżej o 2 cm od początkowego odczytu. Zapisuje raport do sprawdzenia; nie jest usługą ani encją HA, a instalacja przez HACS nie udostępnia tych poleceń. Zacznij od kroku kontrolnego bez ruchu. Fizyczny ruch i Stop nie zostały jeszcze sprawdzone na biurku właściciela.

<a id="help"></a>

## 📚 Pomoc i dokumentacja

- **Coś nie działa?** [Zgłoś błąd](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml).
- **Śledź rozwój:** [Lista zmian](../CHANGELOG.md) · [Plan rozwoju](../docs/roadmap.md).
- **Chcesz pomóc?** [Contributing](../CONTRIBUTING.md) · [Instrukcje dla agentów](../AGENTS.md).
- **Szczegóły techniczne:** [Protokół](../docs/protocol.md) · [Architektura](../docs/architecture.md) · [Plan sterowania](../docs/movement.md).
- **Bezpieczeństwo:** [Prywatne zgłaszanie podatności](../SECURITY.md) · [Utrzymanie według Tier 2](../docs/governance.md). Diagnostyka pomija identyfikatory urządzenia.

Dokumentacja techniczna jest prowadzona po angielsku.

<a id="license"></a>

## 📄 Licencja

Kod: [MIT](../LICENSE). Niezależny projekt społecznościowy, niezwiązany z LINAK ani IKEA. Projekt nie ma oficjalnej oceny jakości HA ani akceptacji do domyślnego katalogu HACS.

Dostarczone oficjalne grafiki LINAK służą identyfikacji sprzętu. Nazwy i grafiki pozostają własnością odpowiednich właścicieli i są wyłączone z licencji kodu. Zobacz [pochodzenie grafik](../docs/branding.md) i [źródła protokołu](../docs/protocol.md).

Szczegóły techniczne: [badania Bluetooth i projekt diagnostyki](../docs/bluetooth-research.md) (po angielsku).
