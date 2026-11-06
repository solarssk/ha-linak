# Security policy

[English](#english) · [Polski](#polski)

## English

### Supported versions

Security fixes are maintained for the latest public release, not every older version. Installations require Home Assistant 2026.11.0 or newer; this minimum is not a promise that every future HA version has been tested.

| Version or installation | Security maintenance |
| --- | --- |
| Latest published release | Supported; fixes are delivered in a new release, not by modifying an existing tag |
| Older public releases | Not maintained separately; update to the latest release |
| Unpublished alpha snapshots | Not supported |
| Current `main` | Development fixes only; not a substitute for a published, validated release |
| Any installation on HA below 2026.11.0 | Unsupported |

0.1.0 is the first public release. Fixes made after the latest published release are available on `main` after review and merge until the next release is published. Check [GitHub Releases](https://github.com/solarssk/ha-linak/releases) for the latest release and [the changelog](CHANGELOG.md) for requirements and limitations.

### Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/solarssk/ha-linak/security/advisories/new), not a public issue. Include:

- Integration and HA versions, identifying a release or development revision
- Affected component, expected/actual behavior and potential impact
- Existing observations or the smallest safe reproduction, with sanitized evidence

Never publish credentials, tokens, device/client identifiers, Bluetooth addresses or unredacted logs. Do not repeat unexpected movement, induce a link loss during travel or change pairing/settings to demonstrate a vulnerability. Explain the observation you already have.

The maintainer assesses reports and coordinates fixes and disclosure through the private advisory. There is no guaranteed response deadline or paid support service.

**If sensitive data was posted publicly, remove it and revoke exposed credentials** before continuing privately.

Ordinary connection, setup and UI bugs belong in the [bug report form](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml). Follow the [diagnostic guide](docs/diagnostics.md#prepare-a-bug-report) for safe evidence collection.

### Physical and software boundaries

LINAK runs inside Home Assistant using HA-managed Bluetooth, locally or through a compatible proxy. It adds no standalone network server, but it can execute explicit movement commands and write supported desk settings, including calibration and reminder configuration.

Keep these limits in mind:

| Boundary | What it means |
| --- | --- |
| Remote Stop | Bluetooth loss can prevent delivery; keep physical stopping access |
| Measured command bounds | Do not replace firmware limits or anti-collision protection |
| Occupancy | The integration does not detect people or obstacles |
| Assurance | No independent security audit; software checks do not certify physical safety |

See the [hardware validation limits](docs/hardware-results.md#hardware-acceptance-matrix).

## Polski

### Wspierane wersje

Poprawki bezpieczeństwa obejmują najnowsze publiczne wydanie, a nie każdą starszą wersję. Wymagany jest Home Assistant 2026.11.0 lub nowszy; to minimum nie oznacza przetestowania każdej przyszłej wersji HA.

| Wersja lub instalacja | Utrzymanie bezpieczeństwa |
| --- | --- |
| Najnowsze opublikowane wydanie | Wspierane; poprawki trafiają do nowego wydania, bez zmieniania istniejącego tagu |
| Starsze publiczne wydania | Bez osobnego utrzymania; zaktualizuj do najnowszej wersji |
| Nieopublikowane wersje alfa | Niewspierane |
| Bieżące `main` | Poprawki rozwojowe; nie zastępuje opublikowanego, zweryfikowanego wydania |
| Dowolna instalacja na HA poniżej 2026.11.0 | Niewspierana |

0.1.0 jest pierwszym publicznym wydaniem. Poprawki wprowadzone po ostatnim opublikowanym wydaniu są dostępne na `main` po przeglądzie i scaleniu, do czasu opublikowania kolejnego wydania. Najnowsze wydanie sprawdzisz w [GitHub Releases](https://github.com/solarssk/ha-linak/releases), a wymagania i ograniczenia w angielskim [changelogu](CHANGELOG.md).

### Zgłoś podatność prywatnie

Użyj [prywatnego zgłoszenia podatności GitHub](https://github.com/solarssk/ha-linak/security/advisories/new), nie publicznego zgłoszenia błędu. Podaj:

- Wersje integracji i HA, ze wskazaniem wydania lub rewizji rozwojowej
- Komponent, oczekiwane i rzeczywiste zachowanie oraz możliwe skutki
- Istniejące obserwacje lub najmniejszy bezpieczny sposób odtworzenia, z oczyszczonymi dowodami

Nie publikuj danych logowania, tokenów, identyfikatorów urządzeń i klientów, adresów Bluetooth ani nieoczyszczonych logów. Nie powtarzaj nieoczekiwanego ruchu, nie zrywaj połączenia podczas jazdy i nie zmieniaj parowania ani ustawień w celu pokazania podatności. Opisz już zaobserwowane zdarzenie.

Opiekun projektu ocenia zgłoszenia oraz uzgadnia poprawkę i ujawnienie w prywatnym zgłoszeniu. Nie ma gwarantowanego terminu odpowiedzi ani usługi płatnego wsparcia.

**Jeśli dane wrażliwe trafiły do publicznego wpisu, usuń je i unieważnij ujawnione dane dostępowe**, zanim przejdziesz do rozmowy prywatnej.

Zwykłe błędy połączenia, konfiguracji i interfejsu zgłaszaj przez [polski formularz błędu](https://github.com/solarssk/ha-linak/issues/new?template=bug.pl.yml). [Instrukcja diagnostyczna po polsku](docs/diagnostics.pl.md) opisuje bezpieczne zebranie danych.

### Granice bezpieczeństwa

LINAK działa wewnątrz Home Assistanta i korzysta z zarządzanego przez HA Bluetooth, lokalnie lub przez zgodne proxy. Nie dodaje osobnego serwera sieciowego, ale może wykonywać jawne polecenia ruchu i zapisywać obsługiwane ustawienia biurka, w tym kalibrację i przypomnienia.

Pamiętaj o ograniczeniach:

| Granica | Znaczenie |
| --- | --- |
| Zdalny Stop | Utrata Bluetooth może uniemożliwić dostarczenie; zachowaj możliwość fizycznego zatrzymania |
| Zmierzony zakres poleceń | Nie zastępuje limitów firmware ani ochrony antykolizyjnej |
| Obecność | Integracja nie wykrywa ludzi ani przeszkód |
| Potwierdzenie bezpieczeństwa | Brak niezależnego audytu; testy oprogramowania nie certyfikują bezpieczeństwa fizycznego |

Zobacz [ograniczenia walidacji sprzętowej](docs/hardware-results.md#hardware-acceptance-matrix).
