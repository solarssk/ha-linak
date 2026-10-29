# LINAK dla Home Assistant

Własna integracja Home Assistanta przygotowywana do dystrybucji przez HACS. Pierwszym obsługiwanym panelem jest DPG1C. Całość działa bezpośrednio w Home Assistant; Mac służy wyłącznie do badań i testów.

## Lokalna wersja alfa 0.1.0a1

Ta wersja odczytuje wysokość w centymetrach, korektę wysokości, maksymalnie cztery zapisane pozycje i trzy profile przypomnień. Konfiguracja odbywa się w interfejsie HA. Sterowanie ruchem i zmiana ustawień nie są jeszcze dostępne.

Siedem zapytań potwierdzono na fizycznym DPG1C. Integrację i klienta Python sprawdzono w Home Assistant 2026.10.2 z symulowanym Bluetooth. Test na Malinie i przez ESPHome Bluetooth Proxy pozostaje do wykonania.

## Instalacja do testów

1. Skopiuj folder `custom_components/ha_linak` do folderu `custom_components` w konfiguracji Home Assistanta.
2. Uruchom ponownie Home Assistant.
3. Zamknij aplikacje połączone z biurkiem. Jeżeli oficjalna integracja IKEA Idasen Desk obsługuje już to biurko, wyłącz jej wpis przed testem.
4. Włącz parowanie Bluetooth na panelu.
5. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację** i wyszukaj LINAK. Wybierz naszą integrację o domenie `ha_linak`; wbudowany wpis marki LINAK prowadzi do innej integracji, IKEA Idasen Desk. Możesz też skorzystać z karty wykrytego urządzenia naszej integracji.
6. Wybierz biurko. Integracja sprawdzi połączenie i rozszerzone odczyty.

Potrzebny jest adapter Bluetooth w zasięgu biurka lub aktywne proxy ESPHome. Przy lokalnym adapterze może być konieczne parowanie na hoście HA. Panel udostępnia jedno połączenie, więc aplikacja telefonu może blokować dostęp.

Wysokość aktualizuje się przy zmianach zgłaszanych przez panel. Co 60 sekund integracja sprawdza połączenie i odświeża ustawienia. Po wykryciu błędu czujniki stają się niedostępne; integracja ponawia próbę odczytu.

Aby usunąć integrację, usuń jej wpis w HA, usuń folder `custom_components/ha_linak` i ponownie uruchom HA. Ta wersja nie zmienia ustawień panelu.

Publiczne repozytorium: [solarssk/ha-linak](https://github.com/solarssk/ha-linak). W HACS dodaj ten adres jako własne repozytorium typu Integracja, pobierz LINAK i uruchom ponownie HA. Projekt nie jest w domyślnym katalogu HACS i nie ma oficjalnej oceny jakości Home Assistanta. Status kontroli znajdziesz w zakładce Actions.

Kontrole CI instalują zależności z plików z hashami i sprawdzają ich zgodność z testowaną wersją HA. Zmiany w narzędziach i pakiecie testowym HA są utrzymywane osobno. Szczegóły dla autorów zmian: [CONTRIBUTING.md](CONTRIBUTING.md).

Codecov i Sonar otrzymują raporty pokrycia integracji oraz wyniki testów w osobnym zadaniu CI. PR-y z forków i od Dependabota nie otrzymują sekretów do wysyłania raportów.
