import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
const require = createRequire(new URL("../web/package.json", import.meta.url));
const { chromium } = require("playwright");
const origin = process.argv[2] ?? "http://127.0.0.1:5173/";
await mkdir("data/replay-pits", { recursive: true });
const browser = await chromium.launch({
  channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
  headless: true,
});
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`${origin}?season=2025&race=1`);
    await page.getByRole("button", { name: /^Pit stops/ }).click();
    const slider = page.getByRole("slider", {
      name: "Replay time",
      exact: true,
    });
    const initial = await slider.inputValue();
    // An incomplete visit must not acquire a duration or playable clip.
    await page
      .locator('[aria-label="All pit visits"] button')
      .filter({ hasText: "incomplete" })
      .first()
      .click();
    assert.equal(
      await page
        .getByRole("button", { name: "Watch this stop", exact: true })
        .isDisabled(),
      true,
    );
    assert.equal(await slider.inputValue(), initial);
    await page
      .getByRole("button", { name: "Close pit stop inspector" })
      .click();
    // Grouped markers open a chronological, keyboard-operable selection list.
    const group = page
      .locator(".markers button")
      .filter({ hasText: /^\d+$/ })
      .first();
    await group.focus();
    await group.press("Enter");
    assert.ok(
      (await page
        .locator('[aria-label="Nearby timeline events"] button')
        .count()) > 2,
    );
    await page
      .getByRole("button", { name: "Close event list", exact: true })
      .click();
    await page
      .locator('[aria-label="All pit visits"] button')
      .filter({ hasText: "recorded" })
      .first()
      .click();
    const inspector = page.locator(".pit-inspector");
    assert.match(await inspector.innerText(), /Recorded entry and exit/);
    assert.equal(await slider.inputValue(), initial);
    await page
      .getByRole("button", { name: "Watch this stop", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Pause replay", exact: true })
      .waitFor();
    const start = Number(await slider.inputValue());
    assert.ok(start > 0);
    // Fast-forward wall time to exercise the actual animation-loop clip endpoint.
    await page.clock.install();
    await page.clock.runFor(1000);
    await page.clock.fastForward(60000);
    await page
      .getByRole("button", { name: "Play replay", exact: true })
      .waitFor();
    const end = Number(await slider.inputValue());
    const bundle = await (
      await page.request.get(`${origin}data/races/2025-01/bundle.json`)
    ).json();
    const entry = Math.min(
      ...bundle.laps
        .filter((row) => row.driver_code === "NOR" && row.pit_entry_t_s != null)
        .map((row) => row.pit_entry_t_s),
    );
    const exit = Math.min(
      ...bundle.laps
        .filter((row) => row.driver_code === "NOR" && row.pit_exit_t_s > entry)
        .map((row) => row.pit_exit_t_s),
    );
    assert.ok(Math.abs(start - (entry - 5)) < 3);
    assert.ok(Math.abs(end - (exit + 5)) <= 0.5);
    assert.ok(end > start && end - start < 45);
    await page.clock.runFor(1000);
    assert.equal(Number(await slider.inputValue()), end);
    await page
      .getByRole("button", { name: "Continue race", exact: true })
      .click();
    await page.clock.runFor(1000);
    assert.ok(Number(await slider.inputValue()) > end + 3);
    await page
      .getByRole("button", { name: "Watch this stop", exact: true })
      .click();
    // Seeking cancels the old endpoint; pause to inspect simultaneous lane traffic.
    await slider.evaluate((el) => {
      el.value = "289";
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page
      .getByRole("button", { name: "Pause replay", exact: true })
      .click();
    assert.ok((await page.locator(".lane-row").count()) > 1);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await page.screenshot({
      path: `data/replay-pits/inspection-${width}.png`,
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 1,
      ),
      false,
    );
    await page
      .getByRole("button", { name: "Play replay", exact: true })
      .click();
    await page.clock.fastForward(60000);
    await page.clock.runFor(100);
    assert.ok(Number(await slider.inputValue()) > end + 20);
    await page
      .getByRole("button", { name: "Close pit stop inspector" })
      .click();
    assert.equal(await inspector.count(), 0);
    await page
      .getByRole("button", { name: "Play replay", exact: true })
      .waitFor();
    // Selecting another visit cancels a clip without seeking; changing drivers closes it.
    await page.locator('[aria-label="All pit visits"] button').first().click();
    await page
      .getByRole("button", { name: "Watch this stop", exact: true })
      .click();
    const beforeNext = Number(await slider.inputValue());
    await page
      .getByRole("button", { name: "Next visit →", exact: true })
      .click();
    assert.ok(Math.abs(Number(await slider.inputValue()) - beforeNext) < 15);
    assert.equal(
      await page
        .getByRole("button", { name: "Watch this stop", exact: true })
        .count(),
      1,
    );
    await page
      .getByRole("button", { name: "Clear driver selection", exact: true })
      .click();
    assert.equal(await inspector.count(), 0);
    await page
      .locator('[aria-label="All pit visits"] button')
      .filter({ hasText: "recorded" })
      .first()
      .click();
    await page
      .getByRole("button", { name: "Watch this stop", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "Race", exact: true })
      .selectOption("2025-02");
    await page
      .getByRole("heading", { name: "Chinese Grand Prix", exact: true })
      .waitFor();
    assert.equal(await inspector.count(), 0);
    assert.equal(Number(await slider.inputValue()), 0);
    assert.deepEqual(errors, []);
    await page.close();
  }
  console.log(
    "PASS pit inspection, grouped selection, incomplete timing, simultaneous visits, focused playback and manual cancellation at 1440/390",
  );
} finally {
  await browser.close();
}
