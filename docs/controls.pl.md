# Ustawienia i sterowanie

[English](controls.md) · **Polski**

Ten poradnik opisuje konfigurację zakresu, korektę wysokości i przypomnienia. Szczegółowe [stany operacji i procedura testów sprzętowych](controls.md#operation-sensor) są osobnym materiałem po angielsku.

Przyciski **Pozycja 1–4** zlecają ruch. Czujniki **Zapisana wysokość 1–4** tylko pokazują zapisane wartości. **Pierwsze testy wymagają obecności przy biurku i możliwości fizycznego zatrzymania.** Pełny dojazd i dokładność Stop pozostają niezweryfikowane.

## Zakres i korekta wysokości

Przed ruchem skonfiguruj zakres:

1. Otwórz **Ustawienia → Urządzenia i usługi → LINAK → Konfiguruj**.
2. Wpisz obie zmierzone granice wysokości. Pozycje pamięci widoczne w kreatorze nie są limitami i nie wypełniają pustych pól.
3. Przy korekcie wysokości pozostaw biurko nieruchome, wpisz pomiar od podłogi do blatu i sprawdź propozycję przed potwierdzeniem.

**Tylko monitorowanie** pozwala skonfigurować odczyty bez zapisu na panelu i bez zakresu. Zakres dodasz później przez **Konfiguruj**.

Oznaczenia zapisanych pozycji w kreatorze:

| Oznaczenie | Znaczenie |
| --- | --- |
| Wysokość w cm | Poprawny odczyt zajętej pamięci, nie potwierdzony pomiar miarką |
| `-` | Pusta pamięć |
| `?` | Brak dostępnego odczytu |
| `n/a` | Nieobsługiwany numer pamięci |

Brakujące granice są puste, nie ustawione na 0 cm. Istniejące pomiary pozostają bez zmian. Zmierzony zakres ogranicza polecenia HA, ale nie zastępuje limitów firmware ani ochrony antykolizyjnej.

## Przypomnienia

Przypomnienia zmienisz na stronie urządzenia w sekcji **Konfiguracja**:

1. Poczekaj na poprawne odczyty i pozostaw biurko nieruchome. Zapis wymaga aktywnego klienta.
2. Wybierz **Wyłączone** lub inny profil przed zmianą czasu. Wybór profilu zachowuje czasy; nie porusza biurkiem i nie aktywuje klienta.
3. Włącz potrzebne pole czasu w ustawieniach encji i wpisz **1–60 pełnych minut**.
4. Po błędzie sprawdź rzeczywiste ustawienie po odzyskaniu połączenia, zanim ponowisz zapis. Nie ma automatycznego ponowienia ani cofnięcia.

Ważne zasady przypomnień:

- Wszystkie sześć pól i przycisk standardowego czasu są domyślnie wyłączone dla nowych encji. Istniejące nazwy i wybory włączenia pozostają bez zmian.
- Czujniki czasów nadal są włączone. Ukrycie pola nie wyłącza przypomnień panelu i nie zmienia odczytów Bluetooth.
- Edycja zmienia tylko wybrany czas. **Profil 1: ustaw standardowy czas** ustawia tylko czas siedzenia profilu 1 na **55 minut**, bez resetu.
- Wartości poza zakresem pozostają widoczne bez automatycznego nadpisywania. Zakres pola nie jest limitem firmware ani zaleceniem medycznym.
- Na sprzęcie sprawdzono tylko 50/55 minut w nieaktywnym profilu 1. Wybór profili 1/2 wymaga jeszcze akceptacji sprzętowej.
- Zmiany na panelu mogą pojawić się po około 5–6 minutach. Zapis z HA aktualizuje stan po potwierdzonym odczycie.

## Jednostki panelu

W **Preferowane jednostki panelu** wybierz **Metryczne** lub **Cale**. Wybór nie zmienia jednostek HA ani zakresu i kalibracji. Opcja Metryczne nie rozróżnia centymetrów i milimetrów.

Panel może nadal pokazywać poprzednią jednostkę. Nie poruszaj biurkiem tylko po to, aby odświeżyć wyświetlacz.

## Ruch i zatrzymanie

Suwak wybiera wysokość co 1 cm wewnątrz zmierzonego zakresu. Czujnik wysokości pokazuje ruch na bieżąco; suwak aktualizuje się po zakończeniu.

Przed kolejnym celem poczekaj na koniec ruchu albo naciśnij **Stop**. Polecenia nie trafiają do kolejki i nie są wznawiane po ponownym połączeniu. Komunikat o zajętości oznacza odrzucenie nowego polecenia, nie dowodzi awarii trwającego ruchu.

Stop nie wymaga skonfigurowanego zakresu, ale potrzebuje gotowego połączenia. Wynik Operacji opisuje wykonanie polecenia, nie jest niezależnym dowodem fizycznego zatrzymania. **Utrata Bluetooth może uniemożliwić zdalny Stop.**

## Utrzymuj połączenie

Encja **Utrzymuj połączenie** jest domyślnie wyłączona w rejestrze. Po jej włączeniu możesz użyć przełącznika do zwolnienia połączenia:

| Działanie | Wynik |
| --- | --- |
| Wyłącz przełącznik | Wstrzymaj odczyty i ponowne łączenie, także po restarcie |
| Wyłącz podczas jazdy | Najpierw próba zatrzymania; jeśli nie potwierdzi się, sprawdź biurko i użyj panelu fizycznego |
| Włącz przełącznik | Połącz i odczytaj dane, bez celu ruchu, kalibracji ani aktywacji klienta |
| Biurko niedostępne po włączeniu | Zgłoś błąd; zamiar pozostaje włączony, a HA ponawia próby według swojego harmonogramu |

Zwolnienie połączenia nie dowodzi uśpienia panelu ani wyłączenia jego wyświetlacza.

## Problem ze sterowaniem

Zacznij od [polskiej instrukcji diagnostycznej](diagnostics.pl.md). Nie powtarzaj nieoczekiwanego ruchu dla zebrania logów. [Rejestr dowodów sprzętowych po angielsku](hardware-results.md) odróżnia zaobserwowane zachowanie od nieukończonych testów.
