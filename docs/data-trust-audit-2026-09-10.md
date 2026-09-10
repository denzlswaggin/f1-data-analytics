# Audit důvěryhodnosti dat — 10. 9. 2026

## Rozsah a verdikt

Read-only audit mergů #62–#68, stav `origin/main` na `96fc7a2`.
Kontrolován kód, SQL vstupy, texty a metriky Evidence dashboardu a snapshot
`20260910T2200-racecraft` (vytvořen 10. 9., nejnovější reprezentovaný závod
23. 8. 2026). Lokální kód odpovídá mergnutému obsahu. Výpočty a uložená
data nebyly během auditu změněny; jediný nový soubor je tento report.

**Dashboard jako celek zatím nelze označit za validovaný a důvěryhodný pro
hodnocení jezdců nebo strategických rozhodnutí.** Obsahuje užitečné popisné
analýzy, ale audit reprodukoval chyby, které mění hodnocení konkrétních jezdců
nebo význam grafu. Úspěšné CI ověřuje implementované testy, nikoli pravdivost
metodiky. Checksum chrání integritu souboru, nikoli správnost závěru.

## Prokázané nálezy

### P1: Skutečný pit-stop vstupuje do clean-air pace a consistency

- `analytics/traffic.py:217`: pit kola se vyřazují podle změny stintu.
- `analytics/pipeline.py:552`: vstup nemá skutečné pit-stop události.
- Pět skutečných pit kol ze `staging.stg_pitstops` přežívá filtr traffic martu.
- Monaco 2025, RUS, kolo 62: skutečný pit záznam má duration 25.063 s,
  ale kolo má `clean_air` a `lap_eligible=True` v consistency.
- Residuum kola je **18.657294 s**. Publikovaný součet nevysvětlené ztráty
  je **20.418104 s**, resp. **10.746371 s / 10 kol**, confidence `medium`.
- Read-only přepočet bez tohoto jediného kola dává **2.545768 s**, resp.
  **1.414315 s / 10 kol**. Tím je potvrzen materiální dopad na závěr stránky.

Oprava: kombinovat skutečné pit-in/out události s odhadem podle stintu,
sdílet masku ve všech navazujících analýzách a přepočítat marty i snapshot.
Regresní případ musí zahrnout pit/penalizaci bez změny stintu.

### P1: Race-control zaměňuje překročení cílové čáry za ztrátu kola

- `analytics/race_control_impact.py:341`: checkpoint se váže na průjezd
  lídra do dalšího kola.
- `analytics/race_control_impact.py:425`: lap deficit vychází z rozdílu
  celočíselných čísel kol v jediném okamžiku.
- Bahrain 2025, RUS: gap **8.61 → 1.35 s**, ale deficit **0 → 1**.
  Jezdec několik sekund za lídrem je tím chybně klasifikován jako měnící
  ztrátu kola a adjusted-time hodnota je potlačena.
- Ve způsobilých SC/VSC řádcích je **517** přechodů 0→1; tento počet není
  individuálním potvrzením všech 517 chyb, ale ukazuje rozsah podezřelé větve.
- **15** způsobilých událostí má jen **jednu** adjusted-gap hodnotu a další
  **4** jen dvě. Medián pouze lídra nepopisuje kompresi pole.
- `analytics/race_control_impact.py:738`: centrování nemá minimální počet
  srovnatelných jezdců; `dashboard/pages/race-control-impact.md:132`
  přesto tvrdí odstranění společné komprese pole.

Oprava: určovat skutečné předjetí o kolo z průběhu vzdálenosti/timing událostí
a zavést minimální velikost srovnatelného pole před výpočtem mediánu.

### P2: Racecraft připisuje rychlé zpětné předjetí opačnému jezdci

- `analytics/racecraft.py:758`: `quick_reversals_made` sčítá původní útoky,
  které soupeř později obrátil, místo úspěšných návratů původního obránce.
- Bahrain 2025: HAM předjíždí NOR v 3799 s, NOR vrací předjetí v 3847 s.
  Summary připisuje rychlý návrat HAM; NOR dostává conceded.
- Snapshot obsahuje **10** takových epizod, všechny způsobilé.

Oprava: obrátit přiřazení obou agregátů a otestovat dvojici jezdců společně.

### P2: Racecraft může uznat obranu bez souvislého 15s otevření gapu

- `analytics/racecraft.py:630`: release timer se nuluje až při návratu
  gapu pod 1.5 s. Návrat do pásma 1.5–2.0 s ho nenuluje.
- Syntetická reprodukce: 10 s tlaku, gap 2.5 s v čase 70, potom 1.8 s
  v časech 71–84, znovu 2.5 s v čase 85. Výsledek je způsobilé `Defended`,
  přestože gap nebyl nad 2 s souvislých 15 s.
- V reálném snapshotu se týká **3 z 778** způsobilých obran:
  2025 R5 battle 72 (HUL/ALB), battle 73 (DOO/ALO),
  2026 R12 battle 184 (TSU/GAS).
- Vedlejší latentní problém: `pressure_seconds = len(pressure) * tick_s`
  sčítá i přerušované úseky, přestože popis hovoří o sustained pressure.
  Synteticky lze získat eligible bez jediné souvislé 10s sekvence.
  V aktuálních 1,824 eligible epizodách ovšem každá alespoň jednu takovou
  souvislou sekvenci má; reálný dopad tohoto druhého problému nebyl nalezen.

Oprava: samostatně sledovat souvislé trvání tlaku a souvislé otevření gapu.

### P2: Pit-window označuje čas pit lane jako čas stání mechaniků

- `dashboard/pages/pit-window-effectiveness.md:122`, `:138`, `:183`
  mluví o stationary time.
- `analytics/pipeline.py:906` používá Jolpica `duration_sec`.
- [Dokumentace Jolpica](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/pitstops.md)
  definuje duration včetně vjezdu, výjezdu a případně času red flagu.
- Medián v datech: **23.5785 s** (2024), **23.1175 s** (2025).
  Např. 2024 R11 PIA 20.775 s, HAM 27.281 s.

Oprava: graf označit jako rozdíl celého průjezdu pit lane. Z těchto vstupů
nelze odděleně hodnotit výkon mechaniků. Samotný pozorovaný net gap swing
tím není automaticky chybný.

### P2: Tyre settling řadí neúplná pozorování jako přesný čas stabilizace

- `analytics/tyre_warmup.py:253` hledá první pozorovanou stabilní dvojici;
  `:468` ji převádí na přesné `time_to_pace_laps`.
- `dashboard/pages/tyre-warmup.md:135` a `:143` z ní vytváří pořadí
  „Which stints took longest?“. Chybějící dřívější kola mohou skutečné
  ustálení skrýt; snížený confidence tento význam neopravuje.
- **13** stabilních řádků má před potvrzením chybějící offsety.
  2025 R4 PIA stint 2: výsledek 6 kol, chybí 2 a 3.
  2026 R4 ALB stint 2: výsledek 6 kol, chybí 2, 3 a 4.

Oprava: publikovat první pozorované potvrzení nebo interval a pro přesné
pořadí vyžadovat úplnou historii. Per-lap residual tím není vyvrácen.

### P2: Traffic pace má společný confidence pro dvě různě podložené metriky

- `analytics/traffic.py:341`: confidence kombinuje clean-air vzorek a
  matching traffic kol, ale clean-air pace se publikuje samostatně od pěti kol.
- **457 z 610** publikovaných clean-air výsledků má `insufficient`.
  **29 z 39** vítězů „Fastest clean-air pace“ má stejný štítek.
- `dashboard/pages/traffic-adjusted-pace.md:145` má jeden sloupec confidence,
  takže uživatel nepozná, ke které metrice nedostatek evidence patří.

Oprava: oddělit evidence pro clean-air pace a traffic association;
headline musí používat odpovídající podmínku způsobilosti.

## Modelová omezení, nikoli prokázané chyby výsledku

**Pit timing sensitivity:** způsobilých je 41 z 2,142 kandidátů (1.9 %),
z toho 12 high. Ve 35/41 případech leží minimum na hranici ±3 kol
(32 dříve, 3 později). To podporuje směr citlivosti v testovaném okně,
nikoli nalezení globálně optimálního kola zastávky.

2025 R9 COL stop 2 například uvádí high a 15.6625 s zisku při zastávce
o tři kola dříve. Starý trend +0.528833 s/kolo je fitován na kolech
30,31,32,33,34,36 před skutečným pitem 39. Model nemá explicitní limit
vzdálenosti extrapolace (`analytics/pit_timing.py:413`, `:443`, `:633`).
Nízká chyba fitu a bootstrap vítězství nevalidují alternativní závod.
Stránka hlavní omezení poctivě přiznává; ponechat experimentální status
a dodat out-of-sample validaci, než se bude „high“ číst jako spolehlivost predikce.

**Racecraft denominator:** 1,824 resolved eligible epizod a 1,046 konverzí
dává přibližně 57.3 %. Dalších 3,049 epizod s nejméně 10 s tlaku je
Interrupted/Unresolved. Míra proto popisuje vybraný soubor rozhodnutých
soubojů, ne pravděpodobnost předjetí při libovolném přiblížení. Wilson interval
nezohledňuje chybu detekce, závislost opakovaných soubojů ani výběr cenzurovaných
epizod. Zobrazit denominator i počty přerušení vedle headline.

**Společné vstupy:** replay pořadí a gapy jsou odvozené interpolací lap progress
(`analytics/replay.py:349`–`:392`). „Confirmed overtake“ znamená potvrzení
heuristikou nad replayem, nikoli nezávisle ověřenou oficiální událost.
`analytics/overtakes.py:140` vytváří confidence váženým heuristickým skóre.
Přesnost detekce proti nezávisle anotovaným skutečným soubojům nebyla tímto
auditem stanovena. Neinterpretovat skóre jako kalibrovanou pravděpodobnost.

## Pokrytí a meze auditu

Další omezení: **9 z 50** eligible race-control událostí má
`recovery_clean=False`, přestože stránka slibuje dvě kompletní racing laps.
Podmínka v `analytics/race_control_impact.py:640` snižuje confidence, ale
nevyřazuje událost. Text či výběr checkpointu je potřeba sladit.

Traffic peer baseline používá aritmetický průměr i při malém vzorku
(`analytics/traffic.py:233`). Singapore 2025, kolo 61: Hamiltonovo pomalé
128.668s kolo zvyšuje Sainzův peer baseline na 103.709 s, takže Sainzovo
94.963s kolo dostává controlled delta −8.746 s. To odpovídá definici
relativní metriky, ale nepředstavuje nezávisle měřenou výkonnost jezdce.
Takové odchylky se přenášejí i do consistency. Robustní peer baseline
a sensitivity test by pomohly. **24 z 39** vítězů „Most repeatable pace“
má navíc low evidence; pořadí bodových odhadů není důkaz stabilního rozdílu.

| Analýza | Aktuální rozsah / způsobilost | Použití nyní |
|---|---|---|
| Traffic-adjusted pace | 34,214 kol; 610 publikovaných clean-air výsledků | Popisné porovnání po opravě pit masky a confidence |
| Pace consistency | Závisí na traffic maskách | Hodnocení pomalého ocasu do opravy nepovažovat za spolehlivé |
| Pit-window | 305/385 matchups eligible | Pozorovaný gap swing; opravit význam pit duration |
| Race-control | 50/66 events eligible | Adjusted-gap závěry vyžadují opravu lap deficit a vzorku |
| Tyre settling | 193/2,142 kandidátů eligible | Pozorované potvrzení; ne přesný žebříček při chybějících kolech |
| Pit timing | 41/2,142 kandidátů eligible | Experimentální sensitivity model |
| Racecraft | 1,824/6,166 episodes eligible | Po opravách; míra pouze mezi způsobilými resolved výsledky |

Replay pokrývá 39 závodů: 4 v roce 2024, 24 v roce 2025 a 11 v roce 2026.
Snapshot je nově sestavený, ale jeho nejnovější reprezentovaný závod je
23. 8. 2026; jeho vlastní kalendář obsahuje i Itálii 6. 9. 2026. Datum exportu
se proto nesmí vydávat za aktuálnost závodních dat. Cache obsahuje i pozdější
závod, což samo o sobě nedokazuje jeho úplné zpracování.

Existují raw ingestion metadata a FastF1 cache; nebyl nalezen důkaz, že by
data byla syntetická. Nebylo provedeno kompletní porovnání všech raw hodnot
s oficiálním timingem. Vizuální interakce v prohlížeči nebyla součástí auditu;
zkontrolovány byly texty, dotazy a skutečné hodnoty snapshotu. Neověřováno,
zda vzdálený veřejný deployment používá přesně tento lokální snapshot.

## Doporučené pořadí oprav

1. Skutečné pit události ve společných filtrech a regresní případ Monaco/RUS.
2. Race-control lap deficit a minimální počet jezdců pro centrování.
3. Racecraft přiřazení reversals a souvislá release podmínka.
4. Pit-lane terminologie, metrické confidence a cenzurované tyre settling.
5. Přepočítat závislé marty a snapshot; porovnat konkrétní nálezy před/po.
6. Přidat referenční anotované závody pro validaci detekce a modelů.

Do té doby je vhodný status produktu **exploratory analytics** s explicitními
omezeními jednotlivých metrik. Výpočty ani deployment nebyly během auditu měněny.
