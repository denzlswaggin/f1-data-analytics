// Run: node --conditions=browser --test scripts/test_dashboard_interactions.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';

const dashboard = new URL('../dashboard/', import.meta.url);
const require = createRequire(new URL('package.json', dashboard));
const { compile } = require('svelte/compiler');
const { JSDOM } = require('jsdom');
const { tick } = await import(pathToFileURL(require.resolve('svelte')));
const directory = await mkdtemp(fileURLToPath(new URL('.evidence/interaction-test-', dashboard)));
const source = await readFile(new URL('components/DriverDNAHeatmap.svelte', dashboard), 'utf8');
const modulePath = `${directory}/Heatmap.mjs`;
await writeFile(modulePath, compile(source, { generate: 'dom' }).js.code);
const { default: Heatmap } = await import(pathToFileURL(modulePath));

test('heatmap exposes detail by activation and clears stale selection when filters change', async () => {
    const dom = new JSDOM('<main></main>');
    globalThis.window = dom.window;
    globalThis.document = dom.window.document;
    const row = { driver_name: 'Driver A', race_label: '2026 R14', metric_label: 'Braking distance', value: 0.25, teammate_name: 'Driver B' };
    const component = new Heatmap({ target: document.querySelector('main'), props: { data: [row] } });
    await tick();
    let cell = document.querySelector('button.cell');
    assert.equal(cell.getAttribute('type'), 'button');
    assert.match(cell.getAttribute('aria-label'), /2026 R14.*0\.25 vs Driver B/);
    cell.click();
    await tick();
    assert.equal(cell.getAttribute('aria-pressed'), 'true');
    assert.match(document.querySelector('[aria-live]').textContent, /Braking distance 0\.25 vs Driver B/);
    cell.click();
    await tick();
    assert.match(document.querySelector('[aria-live]').textContent, /Select a cell/);
    cell.click();
    await tick();
    component.$set({ data: [{ ...row, race_label: '2026 R15', value: -0.12 }] });
    await tick();
    assert.match(document.querySelector('[aria-live]').textContent, /Select a cell/);
    cell = document.querySelector('button.cell');
    assert.equal(cell.getAttribute('aria-pressed'), 'false');
    cell.click();
    await tick();
    assert.match(document.querySelector('[aria-live]').textContent, /2026 R15.*-0\.12/);
    component.$destroy();
    dom.window.close();
});
