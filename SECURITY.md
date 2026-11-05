# Security

LINAK runs inside Home Assistant and uses HA-managed Bluetooth, locally or through a compatible proxy. It adds no standalone network server. It can execute explicit movement commands and write supported desk settings, including the height reference and reminder configuration. It has not received a third-party security audit. Keep physical stopping access; losing Bluetooth can prevent remote Stop.

LINAK działa wewnątrz Home Assistanta i korzysta z zarządzanego przez HA Bluetooth, lokalnie lub przez zgodne proxy. Nie dodaje osobnego serwera sieciowego. Może wykonywać jawne polecenia ruchu i zapisywać obsługiwane ustawienia biurka, w tym punkt odniesienia wysokości i konfigurację przypomnień. Nie przeszło niezależnego audytu bezpieczeństwa. Zachowaj możliwość fizycznego zatrzymania biurka; utrata Bluetooth może uniemożliwić zdalny Stop.

Report vulnerabilities privately through [GitHub private vulnerability reporting](https://github.com/solarssk/ha-linak/security/advisories/new). Do not post credentials, device identifiers or unredacted Bluetooth logs in public issues.

Security fixes target the latest published version and the current development branch; historical unpublished alphas are not maintained separately. Preparing 0.1.0 does not publish it. Dependency updates, secret scanning, tests and HA packaging validators run in CI. These checks do not certify hardware safety or occupancy detection.

Poprawki bezpieczeństwa trafiają do najnowszej opublikowanej wersji i bieżącej gałęzi rozwojowej; historyczne nieopublikowane wersje alfa nie są utrzymywane osobno. Przygotowanie 0.1.0 nie oznacza jego publikacji. Kontrole CI nie potwierdzają bezpieczeństwa fizycznego ani wykrywania obecności.
