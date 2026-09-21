import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';

const require = createRequire(new URL('../web/package.json', import.meta.url));
const { chromium } = require('playwright');
const origin = process.argv[2] ?? 'http://127.0.0.1:4174/f1-data-analytics';
await mkdir('data/important-audit-findings', { recursive: true });
const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
try {
    for (const width of [1440, 390]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 } });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
        async function visit(route) {
            const response = await page.goto(`${origin}/${route}`, { waitUntil: 'networkidle' });
            assert.equal(response.status(), 200, route);
            assert.deepEqual(errors, []);
        }
        async function capture(name) {
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
            await page.screenshot({ path: `data/important-audit-findings/${name}-${width}.png`, fullPage: true });
        }
        await visit('pit-timing-sensitivity/?season=2024&race=13&stop=PER%20%C2%B7%20Stop%202');
        await page.getByText('Experimental scenarios — not stop recommendations', { exact: true }).waitFor();
        await page.getByRole('heading', { name: 'Scenario curve — PER · Stop 2', exact: true }).waitFor();
        assert.equal(await page.getByText('Largest interior timing signal', { exact: true }).count(), 0);
        assert.match(await page.locator('body').innerText(), /only 85 of 2,197 analysed transitions/);
        await capture('pit-timing');
        await visit('saturday-vs-sunday/?minraces=5');
        await page.getByRole('heading', { name: 'Differences and paired uncertainty', exact: true }).waitFor();
        await page.getByText('Race minus qualifying: estimates and paired 90% intervals', { exact: true }).first().waitFor();
        const text = await page.locator('body').innerText();
        assert.match(text, /not adjusted for screening multiple/);
        assert.doesNotMatch(text, /field average|Qualifying specialist|Racer/);
        const intervals = page.locator('figure').filter({ hasText: 'Race minus qualifying: estimates and paired 90% intervals' });
        assert.match(await intervals.innerText(), /Hamilton/);
        assert.match(await intervals.innerText(), /Gasly/);
        await capture('pace-difference');
        await visit('methodology/');
        await page.getByRole('heading', { name: 'Current analytical evidence', exact: true }).waitFor();
        await page.getByText('Passed on this snapshot', { exact: true }).filter({ visible: true }).waitFor();
        assert.ok(await page.getByText('Not evaluated for this snapshot', { exact: true }).filter({ visible: true }).count() >= 3);
        await capture('evidence');
        await visit('driver-ratings/');
        assert.match(await page.locator('body').innerText(), /Career intervals resample undirected comparison edges/);
        await capture('ratings');
        await visit('');
        await page.getByRole('link', { name: 'current analytical evidence summary' }).click();
        await page.waitForURL('**/methodology/#current-analytical-evidence');
        assert.deepEqual(errors, []);
        await page.close();
    }
    console.log('PASS important audit findings at desktop/mobile widths: experimental pit timing, paired uncertainty, dated evidence and scoped claims');
} finally {
    await browser.close();
}
