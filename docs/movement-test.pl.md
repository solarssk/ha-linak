# Test sterowania przy biurku

[🇬🇧 English instructions](movement-test.md)

Ten PR dodaje narzędzie do rzeczywistego testu ruchu i Stop. **Nie dodaje jeszcze encji sterowania do HA — integracja w HACS nadal tylko odczytuje dane.** Test działa na pobliskim komputerze z Bluetooth, poza procesem HA. Nie zmienia offsetu, pamięci, przypomnień ani identyfikatora użytkownika. Wynik programu nie zastępuje obserwacji, czy biurko naprawdę się zatrzymało.

## Przygotowanie

1. Bądź przy panelu. Usuń przeszkody i przygotuj możliwość zatrzymania biurka fizycznym panelem. Na tym etapie nie testuj celowego odcinania zasilania ani Bluetooth.
2. Wyłącz w HA integrację LINAK i ewentualny wpis IKEA Idasen dla tego samego biurka. Zamknij aplikacje biurka na telefonie i komputerze. Poczekaj na zwolnienie połączeń; program nie potrafi zablokować innych komputerów.
3. Przed wyłączeniem HA zapisz odczyt offsetu. Zmierz wysokość bieżącą oraz znane dolne/górne granice ruchu. Wszystkie wartości podajemy w cm; nie wyznaczaj granic z zapisanych pozycji. Parametr offsetu służy tylko przeliczeniu wysokości, niczego nie zapisuje do panelu.
4. Pobierz gałąź tego PR na komputer obok biurka. Korzystaj z osobnego środowiska Python 3.14.2+ według [CONTRIBUTING.md](../CONTRIBUTING.md), a nie z instalowania pakietów wewnątrz HA Core.

Na Macu, w katalogu repozytorium:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m scripts.test_motion_hardware --help
```

Potrzebny jest lokalny identyfikator Bluetooth tego komputera. Na Macu jest to UUID, a nie MAC widoczny na Malinie. Użyj identyfikatora z wcześniejszych prywatnych badań na Macu albo ustal go lokalnie przed testem. Narzędzie nie wyświetla listy urządzeń i nie wykonuje jawnego parowania/usuwania pary. Samo połączenie może uruchomić wykrywanie przez Bleak i uwierzytelnianie systemowe. Problemu z parowaniem nie rozwiązuj resetem biurka.

## 1. Najpierw odczyt, bez poleceń ruchu

Zastąp pola w nawiasach swoimi wartościami. Te zmienne i raporty zostają lokalnie; identyfikatora nie wklejaj na GitHuba.

```sh
DESK_DEVICE='<lokalny identyfikator BLE>'
DESK_OFFSET='<odczytany offset w cm>'
DESK_MIN='<zmierzona dolna granica w cm>'
DESK_MAX='<zmierzona górna granica w cm>'
.venv/bin/python -m scripts.test_motion_hardware --device "$DESK_DEVICE" --offset-cm "$DESK_OFFSET" --minimum-cm "$DESK_MIN" --maximum-cm "$DESK_MAX" > inspection.json
```

W pliku musi być `inspection_only_no_control_writes`. Porównaj `initial_height_cm` z panelem i miarką. Program sprawdza możliwość odczytu wysokości i właściwości zapisu komend. Jeżeli zgłasza błąd lub wysokość się nie zgadza, nie przechodź do ruchu.

## 2. Krótki ruch w górę

Wybierz cel 0,5–1 cm ponad aktualną wysokością, wewnątrz zmierzonych granic i z dala od końców zakresu. W poleceniu użyj kropki dziesiętnej. Program odrzuca cel oddalony o ponad 2 cm od własnego świeżego odczytu. To ograniczenie eksperymentu, nie zabezpieczenie antykolizyjne.

```sh
DESK_TARGET='<wybrana wysokość w cm>'
.venv/bin/python -m scripts.test_motion_hardware --device "$DESK_DEVICE" --offset-cm "$DESK_OFFSET" --minimum-cm "$DESK_MIN" --maximum-cm "$DESK_MAX" --target-cm "$DESK_TARGET" --confirm-supervised-motion > short-up.json
```

Obserwuj kierunek, zatrzymanie i wysokość końcową. Przy nieprawidłowym ruchu natychmiast użyj panelu. Ctrl+C przerywa operację i uruchamia próbę Stop, ale utrata łączności uniemożliwia zagwarantowanie dostarczenia komendy. Nie wciskaj wielokrotnie Ctrl+C i nie zabijaj procesu jako zwykłego sposobu zatrzymania. Kontroler ma limit całej operacji 30 s, braku postępu 2 s i pojedynczego I/O 1 s; to parametry badawcze.

## 3. Stop w trakcie ruchu, potem kierunek w dół

Po udanym krótkim ruchu wybierz nowy pobliski cel, maksymalnie 2 cm od bieżącego odczytu. Uruchom próbę z automatycznym żądaniem Stop po 0,5 s:

```sh
.venv/bin/python -m scripts.test_motion_hardware --device "$DESK_DEVICE" --offset-cm "$DESK_OFFSET" --minimum-cm "$DESK_MIN" --maximum-cm "$DESK_MAX" --target-cm "$DESK_TARGET" --stop-after 0.5 --confirm-supervised-motion > timed-stop.json
```

Czas liczy się od uruchomienia zadania, nie od wykrycia fizycznego ruchu. `completed_before_timed_stop` oznacza, że ruch zakończył się wcześniej — nie zalicza testu przerywania jazdy. `timed_stop_sent_physical_stop_unverified` oznacza zakończenie programowej ścieżki Stop; sam potwierdź, czy biurko stanęło. Po wyjaśnieniu wyników sprawdź oddzielnie krótki ruch w dół. Nie kontynuuj po niewyjaśnionym zachowaniu.

## Co zapisać z każdej próby

- Commit, system, wersje Python/Bleak, rodzaj adaptera; bez MAC/nazwy biurka.
- Model, znany firmware i Full/Limited albo informację „nieznane”.
- Offset, granice oraz wysokość początkową, cel i wynik: z programu, panelu i miarki.
- Rodzaj próby, komendę bez identyfikatora, plik JSON i kod zakończenia.
- Czy ruszyło we właściwą stronę, czy Stop fizycznie zadziałał, opóźnienie/przestrzelenie oraz wskazanie panelu.
- Czy po zakończeniu i ponownym włączeniu LINAK w HA wróciły połączenie i poprawne odczyty.

Kod 0 oznacza zakończenie wybranej ścieżki programu, 1 błąd, 130 przerwanie. `error_type` nie zawiera prywatnego komunikatu backendu. ValueError wymaga sprawdzenia parametrów, właściwości, granic i limitu 2 cm; TimeoutError oznacza przekroczony czas. Pozostałe błędy wymagają sprawdzenia lokalnego Bluetooth. Nie ponawiaj w ciemno, nie zmieniaj właściciela panelu i nie publikuj surowych logów bez sprawdzenia identyfikatorów.

Włącz ponownie tylko LINAK w HA, kiedy program zakończy pracę i biurko fizycznie stoi. Do PR dołącz zanonimizowane raporty i obserwacje. Dopiero te wyniki pozwolą przejść do encji wysokości zadanej i Stop oraz oddzielnych testów współpracy z odświeżaniem i zamykaniem HA. Celowe zrywanie połączenia i badanie zaniku komend zostają na osobny uzgodniony etap.
