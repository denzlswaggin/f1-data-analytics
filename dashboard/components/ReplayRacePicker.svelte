<script>
    import { getInputContext } from '@evidence-dev/sdk/utils/svelte';

    export let seasons = [];
    export let races = [];

    const inputs = getInputContext();

    let seasonRows = [];
    let raceRows = [];
    let selectedSeason = '';
    let selectedRace = '';
    let reconciledSeason = null;

    const rawValue = (name) => $inputs?.[name]?.rawValues?.[0]?.value ?? $inputs?.[name]?.value;
    const sameValue = (left, right) => String(left ?? '') === String(right ?? '');

    function publish(name, value, label) {
        const current = $inputs?.[name];
        if (sameValue(rawValue(name), value) && String(current?.label ?? '') === String(label)) return;

        $inputs[name] = {
            label: String(label),
            value,
            rawValues: [{ value, label: String(label), selected: true }]
        };
    }

    function chooseSeason(event) {
        const option = seasonRows.find((row) => sameValue(row.season, event.currentTarget.value));
        if (!option) return;

        selectedSeason = String(option.season);
        publish('season', option.season, option.season_label);

        const firstRace = raceRows.find((row) => sameValue(row.season, option.season));
        if (firstRace) {
            selectedRace = String(firstRace.round);
            publish('race', firstRace.round, firstRace.race_name);
        }
        reconciledSeason = selectedSeason;
    }

    function chooseRace(event) {
        const option = raceRows.find(
            (row) => sameValue(row.season, selectedSeason) && sameValue(row.round, event.currentTarget.value)
        );
        if (!option) return;

        selectedRace = String(option.round);
        publish('race', option.round, option.race_name);
    }

    $: seasonRows = Array.from(seasons || []);
    $: raceRows = Array.from(races || []);

    $: if (seasonRows.length > 0) {
        const requestedSeason = rawValue('season');
        const season = seasonRows.find((row) => sameValue(row.season, requestedSeason)) || seasonRows[0];
        const nextSeason = String(season.season);
        const seasonChanged = reconciledSeason !== null && reconciledSeason !== nextSeason;

        selectedSeason = nextSeason;
        publish('season', season.season, season.season_label);

        const availableRaces = raceRows.filter((row) => sameValue(row.season, season.season));
        if (availableRaces.length > 0) {
            const requestedRace = seasonChanged ? null : rawValue('race');
            const race = availableRaces.find((row) => sameValue(row.round, requestedRace)) || availableRaces[0];
            selectedRace = String(race.round);
            publish('race', race.round, race.race_name);
        }

        reconciledSeason = nextSeason;
    }
</script>

<div class="race-picker">
    <label>
        <span>Season</span>
        <select value={selectedSeason} on:change={chooseSeason}>
            {#each seasonRows as season}
                <option value={season.season}>{season.season_label}</option>
            {/each}
        </select>
    </label>

    <label>
        <span>Race</span>
        <select value={selectedRace} on:change={chooseRace}>
            {#each raceRows.filter((race) => sameValue(race.season, selectedSeason)) as race}
                <option value={race.round}>{race.race_name}</option>
            {/each}
        </select>
    </label>
</div>

<style>
    .race-picker {
        display: flex;
        align-items: flex-end;
        justify-content: flex-end;
        gap: 0.75rem;
        flex: 1;
        flex-wrap: wrap;
    }
    label {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        min-width: 10rem;
        font-size: 0.76rem;
        font-weight: 600;
    }
    select {
        height: 2rem;
        max-width: 18rem;
        padding: 0 2rem 0 0.65rem;
        border: 1px solid var(--color-base-300, #d7dce1);
        border-radius: 0.4rem;
        background: var(--color-base-100, #fff);
        color: inherit;
        font: inherit;
        font-size: 0.82rem;
        font-weight: 500;
    }
    select:focus-visible {
        outline: 2px solid var(--color-primary, #2563eb);
        outline-offset: 2px;
    }
    @media (max-width: 680px) {
        .race-picker { align-items: stretch; justify-content: stretch; }
        label, select { width: 100%; max-width: none; }
    }
</style>
