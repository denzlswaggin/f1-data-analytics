import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(new URL("../web/package.json", import.meta.url));
const { chromium } = require("playwright");
const origin = process.argv[2] ?? "http://127.0.0.1:4174/f1-data-analytics";
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`${origin}/race-pace/?season=2022&race=1`, {
      waitUntil: "networkidle",
    });
    assert.equal(
      await page
        .getByText("No comparable laps for this duel", { exact: true })
        .count(),
      1,
    );
    await page.goto(
      `${origin}/telemetry/?season=2024&race=1&driver_a=VER&driver_b=VER`,
      { waitUntil: "networkidle" },
    );
    assert.equal(
      await page.getByText("No matched lap pair", { exact: true }).count(),
      1,
    );
    await page.goto(
      `${origin}/telemetry/?season=2024&race=1&driver_a=VER&driver_b=PER`,
      { waitUntil: "networkidle" },
    );
    assert.equal(
      await page.getByText("No matched lap pair", { exact: true }).count(),
      0,
    );
    await page.screenshot({
      path: `data/telemetry-matched-${width}.png`,
      fullPage: true,
    });
    await page.goto(`${origin}/latest-race/`, { waitUntil: "networkidle" });
    const href = await page
      .getByRole("link", { name: "Open this race in the cockpit", exact: true })
      .getAttribute("href");
    assert.match(href, /race-cockpit\/\?season=2026&race=14/);
    await page.goto(`${origin}/driver-ratings/?rating_season=2024`, {
      waitUntil: "networkidle",
    });
    assert.equal(
      await page
        .getByRole("img", {
          name: "Selected-season estimates and 90% weekend-bootstrap intervals",
          exact: true,
        })
        .count(),
      1,
    );
    await page.screenshot({
      path: `data/ratings-intervals-${width}.png`,
      fullPage: true,
    });
    await page.goto(`${origin}/methodology/#metric-definitions`, {
      waitUntil: "networkidle",
    });
    assert.equal(await page.locator("#metric-definitions").count(), 1);
    assert.equal(
      (await page.locator("table").first().locator("tr").count()) > 10,
      true,
    );
    await page.screenshot({
      path: `data/methodology-${width}.png`,
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    await page.close();
  }
  console.log(
    "PASS audit interactions: historical empty baseline, same-driver exclusion, matched duel, scoped cockpit link, rating intervals and method definitions",
  );
} finally {
  await browser.close();
}
