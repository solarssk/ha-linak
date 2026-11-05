# Security policy

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

At this preparation stage, 0.1.0 is not yet published and there are no public releases. Until publication, fixes are available on `main` after review and merge. Check [GitHub Releases](https://github.com/solarssk/ha-linak/releases) for publication and [the changelog](CHANGELOG.md) for requirements and limitations.

### Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/solarssk/ha-linak/security/advisories/new), not a public issue. Include the integration and HA versions, affected component, expected and actual behavior, potential impact and the smallest safe reproduction or sanitized evidence. State whether the report concerns a released version or a development revision.

Never publish credentials, tokens, device/client identifiers, Bluetooth addresses or unredacted logs. Do not repeat unexpected movement, induce a link loss during travel or change pairing/settings to demonstrate a vulnerability. Explain the observation you already have.

The maintainer will assess the report and coordinate a fix and disclosure through the private advisory. There is no guaranteed response deadline or paid support service. If sensitive data was posted publicly, remove it and revoke exposed credentials before continuing privately.

Ordinary connection, setup and UI bugs belong in the [bug report form](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml). Follow the [diagnostic guide](docs/diagnostics.md#prepare-a-bug-report) for safe evidence collection.

### Physical and software boundaries

LINAK runs inside Home Assistant using HA-managed Bluetooth, locally or through a compatible proxy. It adds no standalone network server, but it can execute explicit movement commands and write supported desk settings, including calibration and reminder configuration.

Keep physical stopping access. Bluetooth loss can prevent remote Stop, and measured command bounds do not replace firmware limits or anti-collision protection. The integration does not detect occupancy. It has not received an independent security audit; passing software checks does not certify physical safety. See the [hardware validation limits](docs/hardware-results.md#hardware-acceptance-matrix).

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

Na etapie przygotowania 0.1.0 nie jest jeszcze opublikowane i nie ma publicznych wydań. Do publikacji poprawki są dostępne na `main` po przeglądzie i scaleniu. Publikację sprawdzisz w [GitHub Releases](https://github.com/solarssk/ha-linak/releases), a wymagania i ograniczenia w angielskim [changelogu](CHANGELOG.md).

### Zgłoś podatność prywatnie

Użyj [prywatnego zgłoszenia podatności GitHub](https://github.com/solarssk/ha-linak/security/advisories/new), nie publicznego issue. Podaj wersje integracji i HA, komponent, oczekiwane i rzeczywiste zachowanie, możliwe skutki oraz najmniejszy bezpieczny sposób odtworzenia lub zanonimizowane dowody. Zaznacz, czy dotyczy to wydania, czy rewizji rozwojowej.

Nie publikuj danych logowania, tokenów, identyfikatorów urządzeń i klientów, adresów Bluetooth ani nieoczyszczonych logów. Nie powtarzaj nieoczekiwanego ruchu, nie zrywaj połączenia podczas jazdy i nie zmieniaj parowania ani ustawień w celu pokazania podatności. Opisz już zaobserwowane zdarzenie.

Maintainer oceni zgłoszenie oraz uzgodni poprawkę i ujawnienie w prywatnym zgłoszeniu. Nie gwarantujemy terminu odpowiedzi ani płatnego wsparcia. Jeśli dane wrażliwe trafiły do publicznego wpisu, usuń je i unieważnij ujawnione dane dostępowe, zanim przejdziesz do rozmowy prywatnej.

Zwykłe błędy połączenia, konfiguracji i interfejsu zgłaszaj przez [polski formularz błędu](https://github.com/solarssk/ha-linak/issues/new?template=bug.pl.yml). [Instrukcja diagnostyczna po polsku](docs/diagnostics.md#zgłoszenie-i-logi-po-polsku) opisuje bezpieczne zebranie danych.

### Granice bezpieczeństwa

LINAK działa wewnątrz Home Assistanta i korzysta z zarządzanego przez HA Bluetooth, lokalnie lub przez zgodne proxy. Nie dodaje osobnego serwera sieciowego, ale może wykonywać jawne polecenia ruchu i zapisywać obsługiwane ustawienia biurka, w tym kalibrację i przypomnienia.

Zachowaj możliwość fizycznego zatrzymania biurka. Utrata Bluetooth może uniemożliwić zdalny Stop, a zmierzony zakres poleceń nie zastępuje limitów firmware ani ochrony antykolizyjnej. Integracja nie wykrywa obecności. Nie przeszła niezależnego audytu bezpieczeństwa; pozytywne kontrole oprogramowania nie certyfikują bezpieczeństwa fizycznego. Zobacz [ograniczenia walidacji sprzętowej](docs/hardware-results.md#hardware-acceptance-matrix).
