import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(new URL('../web/package.json', import.meta.url));
const { chromium } = require('playwright');

const origin = process.argv[2] ?? 'http://127.0.0.1:4174/f1-data-analytics';
const routes = [
	'',
	'race-cockpit',
	'latest-race',
	'race-pace',
	'traffic-adjusted-pace',
	'pit-strategy',
	'pit-window-effectiveness',
	'pit-timing-sensitivity',
	'race-control-impact',
	'tyre-strategy',
	'tyre-warmup',
	'telemetry',
	'weather-and-speed',
	'driver-ratings',
	'driver-comparison',
	'driver-dna',
	'pace-consistency',
	'racecraft-battles',
	'saturday-vs-sunday',
	'methodology'
];

async function waitForServer(page) {
	for (let attempt = 0; attempt < 30; attempt += 1) {
		try {
			const response = await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded' });
			if (response?.ok()) return;
		} catch {
			// The static server may still be starting.
		}
		await new Promise((resolve) => setTimeout(resolve, 500));
	}
	throw new Error(`Dashboard server did not start at ${origin}`);
}

const browser = await chromium.launch({ headless: true });
try {
	for (const viewport of [
		{ width: 1440, height: 1000 },
		{ width: 390, height: 844 }
	]) {
		const page = await browser.newPage({ viewport });
		await waitForServer(page);
		for (const route of routes) {
			const errors = [];
			const onPageError = (error) => errors.push(error.message);
			const onConsole = (message) => {
				if (message.type() === 'error') errors.push(message.text());
			};
			page.on('pageerror', onPageError);
			page.on('console', onConsole);
			const response = await page.goto(`${origin}/${route ? `${route}/` : ''}`, {
				waitUntil: 'networkidle'
			});
			assert.equal(response?.status(), 200, `${route || 'home'} should return 200`);
			assert.equal(await page.locator('h1').count(), 1, `${route || 'home'} should have one h1`);
			assert.equal(errors.length, 0, `${route || 'home'} browser errors: ${errors.join('; ')}`);
			const overflow = await page.evaluate(() => ({
				overflows: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
				width: document.documentElement.scrollWidth,
				viewport: document.documentElement.clientWidth,
				offenders: [...document.querySelectorAll('body *')]
					.filter((element) => {
						const bounds = element.getBoundingClientRect();
						return bounds.right > document.documentElement.clientWidth + 1 || bounds.left < -1;
					})
					.slice(0, 5)
					.map((element) => `${element.tagName.toLowerCase()}.${element.className}`)
			}));
			assert.equal(
				overflow.overflows,
				false,
				`${route || 'home'} horizontal overflow ${overflow.width}/${overflow.viewport}: ${overflow.offenders.join(', ')}`
			);
			page.off('pageerror', onPageError);
			page.off('console', onConsole);
		}
		await page.close();
	}
} finally {
	await browser.close();
}

console.log(`PASS dashboard smoke: ${routes.length} routes at desktop and mobile widths`);
