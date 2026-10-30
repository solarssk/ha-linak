<p align="center">
  <img src="custom_components/ha_linak/brand/logo.png" alt="LINAK" width="360">
</p>

# ha-linak

Twoje biurko LINAK w Home Assistant: aktualna wysokość w centymetrach, zapisane pozycje i ustawienia przypomnień. Ta społecznościowa integracja działa bezpośrednio w Home Assistant i jest instalowana przez HACS. Pierwszym obsługiwanym panelem jest **DPG1C**.

[![CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml)
[![Licencja: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![HACS: custom](https://img.shields.io/badge/HACS-custom-orange.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge)](https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak)

[English](README.md) · **Polski**

[Funkcje](#funkcje) · [Instalacja](#instalacja) · [Codzienne użytkowanie](#codzienne-użytkowanie) · [Zgodność](#zgodność) · [Dokumentacja](#dokumentacja) · [Licencja](#licencja)

> [!IMPORTANT]
> **Wersja alfa, tylko odczyt.** Integracja odczytuje dane biurka. Ruch, Stop i zmiana ustawień panelu nie są jeszcze dostępne. Warstwa badawcza sterowania pozostaje odłączona od działającej integracji do czasu nadzorowanego testu na biurku. Zobacz [plan sterowania](docs/movement.md).

## Funkcje

| W Home Assistant | Co można odczytać |
| --- | --- |
| Aktualna wysokość | Wysokość w **cm**, z uwzględnieniem korekty zgłaszanej przez panel |
| Korekta wysokości | Punkt odniesienia wysokości panelu, w cm |
| Zapisane pozycje | Maksymalnie cztery zapisane wysokości, w cm |
| Przypomnienia | Aktywny profil oraz czas siedzenia i stania dla trzech profili |

Konfiguracja odbywa się w interfejsie Home Assistanta, z wykrywaniem przez Bluetooth. Do codziennego działania nie potrzeba Maca, brokera MQTT ani własnej karty pulpitu.

## Instalacja

### Zanim zaczniesz

- **Home Assistant 2026.10.4 lub nowszy.** Lokalnie sprawdzono wersję 2026.10.4.
- Adapter Bluetooth w zasięgu biurka lub zgodne **aktywne proxy Bluetooth ESPHome**. Działanie na Malinie i przez proxy wymaga jeszcze testu na rzeczywistym sprzęcie.
- Wolne połączenie Bluetooth na panelu. Zamknij aplikację telefonu i wyłącz integrację IKEA Idasen Desk, jeśli jest połączona z tym samym biurkiem.

### Pobierz przez HACS

1. W HACS otwórz **Własne repozytoria / Custom repositories**.
2. Dodaj poniższy adres, wybierając typ **Integracja / Integration**:

   ```text
   https://github.com/solarssk/ha-linak
   ```

3. Pobierz **LINAK** i uruchom ponownie Home Assistant.
4. Przejdź do sekcji **Połącz biurko** poniżej.

To własne repozytorium HACS, poza domyślnym katalogiem. Nie opublikowano jeszcze wersjonowanego wydania; HACS pobiera obecnie główną gałąź. Przed instalacją sprawdź [stan CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml).

<details>
<summary>Instalacja ręczna</summary>

Skopiuj cały folder [`custom_components/ha_linak`](custom_components/ha_linak) do katalogu `custom_components` w konfiguracji Home Assistanta. Uruchom ponownie HA i wykonaj poniższe kroki połączenia.

</details>

### Połącz biurko

1. Włącz tryb parowania Bluetooth na panelu biurka.
2. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację** i wyszukaj **LINAK**. Możesz też skorzystać z karty wykrytego urządzenia.
3. Wybierz tę integrację o domenie **`ha_linak`** i wskaż biurko. Przed zapisaniem wpisu konfiguracja sprawdzi połączenie i rozszerzone odczyty.

Wbudowany wpis marki LINAK prowadzi do innej integracji, IKEA Idasen Desk. Przy lokalnym adapterze uwierzytelnienie Bluetooth może wymagać także parowania na hoście Home Assistanta.

## Codzienne użytkowanie

Otwórz urządzenie LINAK w **Ustawienia → Urządzenia i usługi**, aby zobaczyć jego encje. Czujnik aktualnej wysokości możesz dodać do pulpitu za pomocą standardowych kart HA. Czujniki zapisanych pozycji pokazują wysokości zapamiętane na panelu; ich wyświetlenie lub wybranie nie porusza biurkiem.

Wysokość aktualizuje się przez powiadomienia Bluetooth. Co **60 sekund** integracja odświeża też ustawienia i sprawdza połączenie. Wykryte rozłączenie lub błąd odświeżania powodują niedostępność encji; Home Assistant ponawia próby, gdy są załadowane. Niejednoznaczne sesje są zamykane przed ponowieniem próby.

Aby odinstalować integrację, usuń jej wpis, usuń folder `custom_components/ha_linak` i uruchom ponownie HA. Ta wersja nie zmienia ustawień zapisanych na panelu.

## Zgodność

Siedem rozszerzonych zapytań odczytu sprawdzono na **jednym fizycznym DPG1C** przez macOS CoreBluetooth. Klienta Python i integrację przetestowano w **Home Assistant 2026.10.4 z symulowanym Bluetooth**, w tym konfigurację, aktualizacje, utratę połączenia, odzyskiwanie i wyładowanie integracji. [Wyniki sprzętowe](docs/hardware-results.md) rozróżniają obserwacje na biurku od symulacji.

- Działanie na Malinie i przez proxy ESPHome nie zostało jeszcze potwierdzone na rzeczywistym sprzęcie.
- Zgodność innych paneli LINAK nie jest potwierdzona. Klient wymaga sprawdzonego formatu rozszerzonych odpowiedzi.
- Komendy ruchu pozostają odłączone. Nie ma encji rolety pokazującej wysokość w procentach.
- Nieznane pola prędkości i liczniki nie są prezentowane jako potwierdzone pomiary. Wysokość biurka nie oznacza wykrywania obecności.

Projekt nie ma oficjalnej oceny jakości Home Assistanta ani akceptacji do domyślnego katalogu HACS.

## Dokumentacja

| Więcej informacji | Zakres |
| --- | --- |
| [Wyniki sprzętowe](docs/hardware-results.md) | Obserwacje na DPG1C |
| [Protokół](docs/protocol.md) | Formaty BLE i źródła badań |
| [Plan sterowania](docs/movement.md) | Projekt kontrolek i nadzorowane testy |
| [Architektura](docs/architecture.md) | Połączenie i budowa integracji |
| [Lista zmian](CHANGELOG.md) · [Plan rozwoju](docs/roadmap.md) | Zmiany i kolejne kroki |

Dla autorów zmian: [Contributing](CONTRIBUTING.md) i [instrukcje dla agentów](AGENTS.md). Repozytorium przyjmuje [wymagania Tier 2](docs/governance.md) z playbooka, obejmujące testy, kontrolę typów, CodeQL, skanowanie zależności i sekretów oraz ochronę głównej gałęzi. Diagnostyka pomija identyfikatory urządzenia. Podatności zgłaszaj zgodnie z [Security](SECURITY.md). Dokumentacja techniczna jest prowadzona po angielsku.

## Licencja

Kod: [MIT](LICENSE). To niezależny projekt społecznościowy, niezwiązany z LINAK ani IKEA.

Nazwy, ikona i logo LINAK służą identyfikacji sprzętu i pozostają własnością odpowiednich właścicieli. Grafiki są wyłączone z licencji MIT kodu. Zobacz [pochodzenie grafik](docs/branding.md) oraz [źródła protokołu](docs/protocol.md).
