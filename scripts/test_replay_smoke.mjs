import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(new URL("../web/package.json", import.meta.url));
const { chromium } = require("playwright");
const origin =
  process.argv[2] ?? "http://127.0.0.1:4175/f1-data-analytics/replay/";
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`${origin}?season=2025&race=1`);
    await page
      .getByText("Replay evidence: recorded, estimated and animated", {
        exact: true,
      })
      .waitFor({ timeout: 60000 });
    assert.match(await page.locator("h1").innerText(), /Australian/);
    await page.locator(".provenance-panel summary").click();
    assert.match(
      await page.locator(".provenance-panel").innerText(),
      /projected from lap progress/,
    );
    await page
      .getByRole("slider", { name: "Replay time", exact: true })
      .evaluate((el) => {
        el.value = "120";
        el.dispatchEvent(new Event("input", { bubbles: true }));
      });
    if (width === 390)
      await page
        .getByRole("button", { name: "Show all drivers", exact: true })
        .click();
    await page.locator(".position[title]").first().waitFor();
    assert.ok((await page.locator(".position[title]").count()) > 0);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1,
      ),
      false,
    );
    assert.deepEqual(errors, []);
    await page.screenshot({
      path: `data/replay-provenance-${width}.png`,
      fullPage: true,
    });
    await page.goto(`${origin}?season=2022&race=1`);
    await page.getByRole("alert").waitFor();
    assert.match(await page.getByRole("alert").innerText(), /requested race/);
    await page.close();
  }
  console.log(
    "PASS replay provenance, scoped race selection and unsupported-race state at 1440/390",
  );
} finally {
  await browser.close();
}
