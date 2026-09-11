// Run: node --conditions=browser --test scripts/test_race_event_dropdown.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL, fileURLToPath } from 'node:url';

const dashboard = new URL('../dashboard/', import.meta.url);
const require = createRequire(new URL('package.json', dashboard));
const { compile } = require('svelte/compiler');
const { JSDOM } = require('jsdom');
const { writable, get } = await import(pathToFileURL(require.resolve('svelte/store')));
const { tick } = await import(pathToFileURL(require.resolve('svelte')));
const { setTrackProxy, hasUnsetValues } = await import(new URL(
    'node_modules/@evidence-dev/sdk/src/usql/setTrackProxy/setTrackProxy.js', dashboard));
const directory = await mkdtemp(fileURLToPath(new URL('.evidence/event-dropdown-test-', dashboard)));
const moduleUrl = (name) => pathToFileURL(`${directory}/${name}`);

await writeFile(moduleUrl('context.mjs'), `
    import { getContext } from 'svelte';
    export const getInputContext = () => getContext('inputs');
`);
// Model Evidence's mount-time restoration of rawValues. A remount alone must
// not resurrect the previous selection before defaultValue is considered.
const dropdown = `<script>
    import { getInputContext } from './context.mjs';
    export let data, name, value, label, order, defaultValue, title;
    const inputs = getInputContext();
    let selected = $inputs[name]?.rawValues?.[0]?.value ?? defaultValue;
    function choose() {
        $inputs[name] = { value: selected, rawValues: [{ value: selected, selected: true }] };
    }
</script>
<select bind:value={selected} on:change={choose}>
    {#each data as row}<option value={row[value]}>{row[label]}</option>{/each}
</select>`;
await writeFile(moduleUrl('Dropdown.mjs'), compile(dropdown, { generate: 'dom' }).js.code);
const source = (await readFile(new URL('components/DependentDropdown.svelte', dashboard), 'utf8'))
    .replace("import { Dropdown } from '@evidence-dev/core-components';", "import Dropdown from './Dropdown.mjs';")
    .replace("'@evidence-dev/sdk/utils/svelte'", "'./context.mjs'");
await writeFile(moduleUrl('DependentDropdown.mjs'), compile(source, { generate: 'dom' }).js.code);
const eventSource = (await readFile(new URL('components/RaceEventDropdown.svelte', dashboard), 'utf8'))
    .replace('./DependentDropdown.svelte', './DependentDropdown.mjs');
await writeFile(moduleUrl('RaceEventDropdown.mjs'), compile(eventSource, { generate: 'dom' }).js.code);
const { default: RaceEventDropdown } = await import(moduleUrl('RaceEventDropdown.mjs'));
const { default: DependentDropdown } = await import(moduleUrl('DependentDropdown.mjs'));

test('race changes select the first event, including delayed results and return visits', async () => {
    const dom = new JSDOM('<main></main>');
    globalThis.window = dom.window;
    globalThis.document = dom.window.document;
    const events = (season, round) => [1, 2].map((number) => ({
        season, round, event_number: number,
        event_id: `${season}-${round}-${number}`, event_label: `Event ${number}`
    }));
    const inputs = writable({ event: { value: 'stale', rawValues: [{ value: 'stale', selected: true }] } });
    const component = new RaceEventDropdown({
        target: document.querySelector('main'),
        context: new Map([['inputs', inputs]]),
        props: { season: 2024, round: 1, data: events(2024, 1) }
    });
    const selected = () => document.querySelector('select:not(:disabled)')?.value;
    const chooseSecond = async () => {
        const select = document.querySelector('select');
        select.selectedIndex = 1;
        select.dispatchEvent(new dom.window.Event('change'));
        await tick();
    };
    await tick();
    assert.equal(selected(), '2024-1-1');
    await chooseSecond();
    assert.equal(get(inputs).event.value, '2024-1-2');
    component.$set({ data: events(2024, 1) });
    await tick();
    assert.equal(selected(), '2024-1-2', 'refreshing the same race preserves a manual choice');

    component.$set({ round: 2 });
    await tick();
    assert.equal(selected(), undefined, 'old options disappear while the new race loads');
    assert.equal(get(inputs).event?.value, undefined);
    component.$set({ data: events(2024, 2) });
    await tick();
    assert.equal(selected(), '2024-2-1');
    assert.equal(get(inputs).event.value, '2024-2-1');
    await chooseSecond();

    component.$set({ round: 1, data: events(2024, 1) });
    await tick();
    assert.equal(selected(), '2024-1-1', 'returning to a race starts at its first event');
    component.$set({ season: 2025, data: events(2025, 1) });
    await tick();
    assert.equal(selected(), '2025-1-1', 'the same round in another season is a different race');
    component.$set({ round: 3, data: [] });
    await tick();
    assert.equal(selected(), undefined);
    assert.equal(get(inputs).event?.value, undefined);
    component.$destroy();
    dom.window.close();
});

function mountDropdown(props, initial = {}) {
    const dom = new JSDOM('<main></main>');
    globalThis.window = dom.window;
    globalThis.document = dom.window.document;
    const inputs = writable(initial);
    const component = new DependentDropdown({ target: document.querySelector('main'),
        context: new Map([['inputs', inputs]]), props });
    return { component, inputs, close: () => { component.$destroy(); dom.window.close(); } };
}

test('season changes always choose the latest round, including overlapping rounds and unsorted data', async () => {
    const races = (season, rounds) => rounds.map(round => ({ season, round, race_label: `R${round}` }));
    const f = mountDropdown({ name: 'race', value: 'round', label: 'race_label', title: 'Race',
        season: 2025, data: races(2025, [1, 24, 23]), latest: true, preserveInitial: true },
        { race: { value: 23, rawValues: [{ value: 23, selected: true }] } });
    await tick();
    assert.equal(get(f.inputs).race.value, 23, 'a valid initial deep link is preserved');
    f.component.$set({ season: 2026 });
    await tick();
    assert.equal(get(f.inputs).race?.value, undefined, 'old season data is ignored');
    f.component.$set({ data: races(2026, [1, 12, 3]) });
    await tick();
    assert.equal(get(f.inputs).race.value, 12);
    f.component.$set({ season: 2024, data: races(2024, [12, 24, 1]) });
    await tick();
    assert.equal(get(f.inputs).race.value, 24, 'even a valid shared round resets on season change');
    f.component.$set({ data: races(2024, [12, 1]) });
    await tick();
    assert.equal(get(f.inputs).race.value, 12, 'a removed round cannot remain selected');
    f.close();
});

test('driver and stop choices reset with the race and recover from empty options', async () => {
    const rows = (round, values) => values.map(driver_code => ({ season: 2026, round, driver_code }));
    const f = mountDropdown({ name: 'driver_b', value: 'driver_code', title: 'Driver B',
        season: 2026, round: 1, data: rows(1, ['ALO', 'LEC', 'VER']), defaultValue: 'LEC', fallbackIndex: 1 });
    await tick();
    assert.equal(get(f.inputs).driver_b.value, 'LEC');
    f.component.$set({ round: 2, data: rows(2, ['ALO', 'NOR', 'VER']) });
    await tick();
    assert.equal(get(f.inputs).driver_b.value, 'NOR', 'a missing preferred driver uses a valid fallback');
    f.component.$set({ round: 3, data: [] });
    await tick();
    assert.equal(get(f.inputs).driver_b?.value, undefined);
    f.component.$set({ data: rows(3, ['VER']) });
    await tick();
    assert.equal(get(f.inputs).driver_b.value, 'VER');
    f.close();

    const stops = (round, values) => values.map(stop_label => ({ season: 2026, round, stop_label }));
    const s = mountDropdown({ name: 'stop', value: 'stop_label', title: 'Stop', season: 2026,
        round: 1, data: stops(1, ['VER Stop 1', 'LEC Stop 2']) });
    await tick();
    s.inputs.set({ stop: { value: 'LEC Stop 2', rawValues: [{ value: 'LEC Stop 2', selected: true }] } });
    s.component.$set({ round: 2, data: stops(2, ['NOR Stop 1', 'LEC Stop 2']) });
    await tick();
    assert.equal(get(s.inputs).stop.value, 'NOR Stop 1');
    s.close();
});

test('Evidence suspends dependent queries until the new options arrive', async () => {
    const tracked = setTrackProxy({ value: '(select null where 0)', label: '' });
    const f = mountDropdown({ name: 'race', value: 'round', title: 'Race', season: 2025,
        data: [{ season: 2025, round: 23 }], latest: true }, tracked);
    await tick();
    assert.equal(hasUnsetValues`${get(f.inputs).race.value}`, false);
    f.component.$set({ season: 2026 });
    await tick();
    assert.equal(hasUnsetValues`${get(f.inputs).race.value}`, true,
        'missing options must remain unresolved rather than publish a real SQL NULL');
    f.component.$set({ data: [{ season: 2026, round: 12 }] });
    await tick();
    assert.equal(get(f.inputs).race.value, 12);
    assert.equal(hasUnsetValues`${get(f.inputs).race.value}`, false);
    f.close();
});
