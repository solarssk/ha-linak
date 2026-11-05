# Integralność artefaktu wydania

[English](release-integrity.md) · **Polski**

Ta instrukcja opisuje paczkę ZIP integracji i fuzzer protokołu. Archiwa źródłowe generowane przez GitHuba są odrębnymi artefaktami i nie obejmuje ich suma kontrolna ani atestacja paczki integracji.

## Weryfikacja archiwum wydania

Pobierz z tego samego GitHub Release pliki `ha_linak.zip`, `ha_linak.zip.sha256` i `ha_linak.intoto.jsonl`. Najpierw sprawdź sumę kontrolną, a następnie atestację kompilacji GitHub opartą na Sigstore oraz jej powiązanie ze źródłowym tagiem:

```sh
shasum -a 256 -c ha_linak.zip.sha256
gh attestation verify ha_linak.zip \
  --repo solarssk/ha-linak \
  --signer-workflow solarssk/ha-linak/.github/workflows/release-artifact.yml \
  --source-ref refs/tags/v0.1.0 \
  --bundle ha_linak.intoto.jsonl
```

Zastąp `v0.1.0` tagiem pobranego wydania. Użyj GitHub CLI w wersji 2.49.0 lub nowszej. Zainstaluj archiwum dopiero po powodzeniu obu poleceń. Paczka zawiera `custom_components/ha_linak/`; suma wykrywa przypadkowe zmiany, a atestacja wiąże skrót archiwum z uruchomieniem tagowanego workflow w tym repozytorium.

## Budowanie i dołączanie artefaktów do wydania

Opiekun projektu osobno tworzy tag i GitHub Release. Ręczny [workflow artefaktu wydania](../.github/workflows/release-artifact.yml) buduje paczkę z wybranego źródła i porównuje jej wersję z `manifest.json` i `CHANGELOG.md`. Domyślnie publikacja jest wyłączona. Uruchomienie na gałęzi buduje i atestuje paczkę kontrolną bez uprawnień do wydania; uruchomienie na tagu sprawdza jego zgodność z wersją integracji.

Aby opublikować artefakty, najpierw utwórz wydanie dla tego tagu, a następnie uruchom workflow na tagu z włączoną opcją `Upload signed assets to an existing GitHub Release for this tag`. Zadanie publikujące weryfikuje atestację i dołącza do istniejącego wydania plik ZIP, sumę SHA-256 i pakiet atestacji. Workflow nie tworzy ani tagu, ani wydania i nie nadpisuje istniejących artefaktów. Archiwa źródłowe generowane przez GitHuba nie są podpisywane przez ten workflow.

Zbuduj lokalnie tę samą paczkę instalacyjną poleceniem:

```sh
python scripts/build_release_artifact.py --output-dir dist
```

Przy budowaniu z tagu podaj również tag, na przykład `--tag v0.1.0`. Archiwum zawiera tylko katalog integracji, nie zawiera kodu bajtowego Pythona ani katalogów cache i używa czasu commitu zamiast bieżącego czasu. Ponowne zbudowanie tego samego commitu tymi samymi wersjami Pythona i zlib daje identyczne bajty ZIP.

## Fuzzing dekoderów protokołu

W systemie Linux x86_64 zainstaluj zależności programistyczne i uruchom ograniczony czasowo fuzzer Atheris:

```sh
python -m pip install -r requirements-dev.txt
python fuzz/fuzz_protocol.py --duration-seconds 30
```

Harness testuje czystymi bajtami dekodery pozycji, możliwości, offsetu, zapisanej pozycji, przypomnień, odpowiedzi badawczych i aktywacji. Sprawdza typy zaakceptowanych wyników i zakresy liczbowe; nieoczekiwany wyjątek przerywa test. CI uruchamia ten sam fuzzer przez 30 sekund w wymaganym zadaniu Tests. Atheris 3.1.0 udostępnia obecnie koło dla Pythona 3.14 tylko dla Linux x86_64, więc standardowe zależności programistyczne macOS go pomijają. Fuzzer nie importuje Home Assistanta, nie skanuje Bluetooth, nie łączy się z biurkiem ani nie wysyła poleceń ruchu. Wykrycie Atheris przez Scorecard nie oznacza rejestracji w OSS-Fuzz ani testu sprzętu.
