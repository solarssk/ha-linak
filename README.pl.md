<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/linak-logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/linak-logo-light.svg">
    <img src="docs/assets/linak-logo-light.svg" alt="LINAK — We improve your life" width="360">
  </picture>
</p>

<h1 align="center">ha-linak</h1>

<p align="center">
  <strong>Twoje biurko LINAK w Home Assistant.<br>Aktualna wysokość w centymetrach, zapisane wysokości i przypomnienia.</strong><br>
  Działa bezpośrednio w Home Assistant. Pierwszy obsługiwany panel: <strong>DPG1C</strong>.
</p>

<p align="center">
  🇬🇧 <a href="README.md">English</a> &nbsp;·&nbsp; 🇵🇱 <strong>Polski</strong>
</p>

<p align="center">
  <a href="hacs.json"><img src="https://img.shields.io/badge/Home%20Assistant-2026.10.4%2B-41BDF5?logo=homeassistant&amp;logoColor=white" alt="Home Assistant 2026.10.4 lub nowszy"></a>
  <a href="https://www.hacs.xyz/docs/faq/custom_repositories/"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&amp;logoColor=white" alt="Własne repozytorium HACS"></a>
</p>

<p align="center">
  <a href="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml"><img src="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak"><img src="https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge" alt="OpenSSF Scorecard"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="Licencja kodu: MIT"></a>
</p>

> [!IMPORTANT]
> **Wersja alfa, tylko odczyt.** Możesz przeglądać dane biurka. Ruch, Stop i zmiana ustawień panelu są jeszcze w przygotowaniu. [Co dalej? →](docs/roadmap.md)

<details>
<summary><strong>Spis treści</strong></summary>

- [Co zobaczysz w HA](#co-zobaczysz-w-ha)
- [Instalacja i połączenie](#instalacja-i-połączenie)
- [Na co dzień](#na-co-dzień)
- [Sprawdzony sprzęt](#sprawdzony-sprzęt)
- [Pomoc i informacje o projekcie](#pomoc-i-informacje-o-projekcie)
- [Licencja](#licencja)

</details>

## Co zobaczysz w HA

| Czujnik | W Home Assistant |
| --- | --- |
| Wysokość biurka | Aktualna wysokość w **cm**, z korektą zgłaszaną przez panel |
| Zapisane wysokości | Maksymalnie **cztery pozycje**, w cm |
| Przypomnienia | Aktywny profil oraz czas siedzenia i stania dla **trzech profili** |
| Korekta wysokości | Punkt odniesienia wysokości panelu, w cm |

## Instalacja i połączenie

**Potrzebujesz:** Home Assistanta **2026.10.4+**, HACS i Bluetooth w zasięgu biurka.

Połączenie może zapewnić lokalny adapter lub zgodne **aktywne proxy Bluetooth ESPHome**. Działanie na Malinie i przez proxy wymaga jeszcze testu na rzeczywistym sprzęcie.

### 1. Pobierz przez HACS

1. Otwórz HACS → **Własne repozytoria / Custom repositories**.
2. Dodaj ten adres i wybierz **Integracja / Integration**:

   ```text
   https://github.com/solarssk/ha-linak
   ```

3. Pobierz **LINAK** i uruchom ponownie Home Assistant.

<details>
<summary>Wolisz instalację ręczną?</summary>

Skopiuj [`custom_components/ha_linak`](custom_components/ha_linak) do folderu `custom_components` w konfiguracji Home Assistanta i uruchom ponownie HA.

</details>

### 2. Połącz biurko

1. Zamknij aplikację telefonu. Wyłącz integrację IKEA Idasen Desk, jeśli używa tego samego biurka.
2. Włącz **tryb parowania Bluetooth** na panelu.
3. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację** i wyszukaj **LINAK** lub skorzystaj z karty wykrytego urządzenia.
4. Wybierz tę integrację o domenie **`ha_linak`**, a następnie swoje biurko.

> [!TIP]
> Panel przyjmuje jedno połączenie Bluetooth naraz. Jeśli konfiguracja się nie udaje, sprawdź, czy nie jest połączona inna aplikacja. Lokalny adapter może też wymagać parowania na hoście HA.

<details>
<summary>O wersji alfa i wbudowanym wpisie LINAK</summary>

- To własne repozytorium HACS, poza domyślnym katalogiem.
- Nie ma jeszcze wersjonowanego wydania; HACS pobiera główną gałąź. Sprawdź [stan CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml).
- Wbudowany wpis LINAK prowadzi do innej integracji, IKEA Idasen Desk. Dla tego projektu wybierz `ha_linak`.

</details>

## Na co dzień

- Znajdziesz czujniki w **Ustawienia → Urządzenia i usługi → LINAK**.
- Dodaj wysokość biurka do pulpitu za pomocą standardowej karty HA.
- Podejrzyj wysokości zapisane na panelu. Ich przeglądanie nie porusza biurkiem.
- Wysokość aktualizuje się przez Bluetooth. Ustawienia odświeżają się co **60 sekund**.
- Po błędzie połączenia czujniki stają się niedostępne, a HA ponawia próby, gdy są załadowane.

<details>
<summary>Usuwanie integracji</summary>

Usuń jej wpis w Home Assistant, usuń folder `custom_components/ha_linak` i uruchom ponownie HA. Ta wersja nie zmienia ustawień zapisanych na panelu.

</details>

## Sprawdzony sprzęt

| Środowisko | Stan |
| --- | --- |
| Jeden fizyczny **DPG1C** | Siedem zapytań odczytu sprawdzonych przez macOS CoreBluetooth |
| **HA 2026.10.4**, symulowany Bluetooth | Testy konfiguracji, czujników, rozłączenia, odzyskiwania i wyładowania integracji |
| Malina / proxy ESPHome | Test na rzeczywistym sprzęcie do wykonania |
| Inne panele LINAK | Zgodność niepotwierdzona |

Szczegóły: [wyniki sprzętowe](docs/hardware-results.md). Nie ma encji rolety z wysokością w procentach. Nieznane pola prędkości i liczniki nie są udostępniane jako potwierdzone pomiary; wysokość nie oznacza wykrywania obecności.

## Pomoc i informacje o projekcie

- **Coś nie działa?** [Zgłoś błąd](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml).
- **Śledź rozwój:** [Lista zmian](CHANGELOG.md) · [Plan rozwoju](docs/roadmap.md).
- **Chcesz pomóc?** [Contributing](CONTRIBUTING.md) · [Instrukcje dla agentów](AGENTS.md).
- **Szczegóły techniczne:** [Protokół](docs/protocol.md) · [Architektura](docs/architecture.md) · [Plan sterowania](docs/movement.md).
- **Bezpieczeństwo:** [Prywatne zgłaszanie podatności](SECURITY.md) · [Utrzymanie według Tier 2](docs/governance.md). Diagnostyka pomija identyfikatory urządzenia.

Dokumentacja techniczna jest prowadzona po angielsku.

## Licencja

Kod: [MIT](LICENSE). Niezależny projekt społecznościowy, niezwiązany z LINAK ani IKEA. Projekt nie ma oficjalnej oceny jakości HA ani akceptacji do domyślnego katalogu HACS.

Dostarczone oficjalne grafiki LINAK służą identyfikacji sprzętu. Nazwy i grafiki pozostają własnością odpowiednich właścicieli i są wyłączone z licencji kodu. Zobacz [pochodzenie grafik](docs/branding.md) i [źródła protokołu](docs/protocol.md).
