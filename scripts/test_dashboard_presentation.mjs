// Run: node --test scripts/test_dashboard_presentation.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';

const dashboard = new URL('../dashboard/', import.meta.url);
const require = createRequire(new URL('package.json', dashboard));
const { compile } = require('svelte/compiler');
const { JSDOM } = require('jsdom');
const directory = await mkdtemp(fileURLToPath(new URL('.evidence/presentation-test-', dashboard)));
async function component(name) {
    const source = await readFile(new URL(`components/${name}.svelte`, dashboard), 'utf8');
    const output = `${directory}/${name}.mjs`;
    await writeFile(output, compile(source, { generate: 'ssr', filename: name }).js.code);
    return (await import(pathToFileURL(output))).default;
}
const SnapshotStatus = await component('SnapshotStatus');
const DataTrust = await component('DataTrust');
const RelatedAnalysis = await component('RelatedAnalysis');
const AppNav = await component('AppNav');
const RatingIntervals = await component('RatingIntervals');
const documentFor = html => new JSDOM(html).window.document;

test('missing or unrecognised freshness never claims data is current', () => {
    for (const status of [undefined, 'unknown', 'unexpected']) {
        const { html } = SnapshotStatus.render({ data: [{ freshness_status: status }] });
        assert.match(html, /Data freshness unverified/);
        assert.doesNotMatch(html, /Snapshot is current/);
        assert.ok(documentFor(html).querySelector('.snapshot-status.unknown'));
    }
    assert.match(SnapshotStatus.render({ data: [{ freshness_status: 'current' }] }).html, /Snapshot is current/);
    assert.match(SnapshotStatus.render({ data: [{ freshness_status: 'stale', freshness_lag_days: 7 }] }).html, /Snapshot needs a data refresh/);
});

test('related links preserve race context and never repeat the current page', () => {
    for (const current of ['race-pace', 'tyre-warmup', 'driver-dna', 'race-cockpit']) {
        const doc = documentFor(RelatedAnalysis.render({ current, season: 2026, race: 14 }).html);
        const links = [...doc.querySelectorAll('a')];
        assert.equal(links.length, 3);
        for (const link of links) {
            const url = new URL(link.href, 'https://example.test');
            assert.notEqual(url.pathname, `/f1-data-analytics/${current}/`);
            assert.equal(url.searchParams.get('season'), '2026');
            assert.equal(url.searchParams.get('race'), '14');
        }
    }
});

test('navigation has one entry per destination and native disclosure groups', () => {
    const doc = documentFor(AppNav.render().html);
    const destinations = [...doc.querySelectorAll('.links a')].map(a => a.href);
    assert.equal(new Set(destinations).size, destinations.length);
    assert.equal(doc.querySelectorAll('.nav-groups > details > summary').length, 3);
    assert.deepEqual(
        [...doc.querySelectorAll('.nav-groups > details:first-child .links a')].map(a => a.textContent.trim()),
        ['Overview', 'Explore a race', 'Compare drivers', 'Methodology']
    );
    assert.doesNotMatch(doc.body.textContent, /Snapshot online/);
});

test('evidence summary shows coverage and distinguishes inputs from usable observations', () => {
    const doc = documentFor(DataTrust.render({ data: [{
        first_season: 2024, last_season: 2026, sample_rows: 120, sample_unit: 'laps',
        usable_samples: 75, usable_unit: 'eligible laps'
    }] }).html);
    const summary = doc.querySelector('summary').textContent;
    assert.match(summary, /Coverage: 2024–2026/);
    assert.match(summary, /Inputs: 120 laps/);
    assert.match(summary, /Usable: 75 eligible laps/);
    assert.match(doc.querySelector('.details').textContent, /Method/);
});

test('compact ratings retain uncertainty, sample sizes and missing-interval state', () => {
    const doc = documentFor(RatingIntervals.render({ data: [
        { driver_name: 'Driver A', rating: 0.2, rating_lo: 0.1, rating_hi: 0.3, n_comparisons: 42 },
        { driver_name: 'Driver B', rating: -0.1, rating_lo: null, rating_hi: null, n_comparisons: 5 }
    ] }).html);
    const rows = [...doc.querySelectorAll('.compact .rating-row')];
    assert.equal(rows.length, 2);
    assert.match(rows[0].textContent, /0\.100 to 0\.300 · 42 comparisons/);
    assert.match(rows[1].textContent, /unavailable · 5 comparisons/);
    assert.equal(rows[1].querySelectorAll('.interval').length, 0);
});
