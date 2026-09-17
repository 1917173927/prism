import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:4173/";
const executablePath = process.env.PRISM_TEST_BROWSER || (
  process.platform === "win32"
    ? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
    : "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
);

const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});
try {
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", message => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", error => consoleErrors.push(error.message));
  await page.setViewport({width: 1440, height: 1000, deviceScaleFactor: 1});
  const snapshotUrl = new URL(baseUrl);
  snapshotUrl.searchParams.set("pages", "1");
  await page.goto(snapshotUrl, {waitUntil: "networkidle0", timeout: 60000});
  await page.waitForFunction(
    () => window.PRISM_PAGES_SNAPSHOT === true
      && document.querySelector("#copilot:not([hidden])")
      && !document.body.classList.contains("questionnaire-pending"),
    {timeout: 30000},
  );

  assert.equal(await page.$("#pages-demo-badge"), null);
  assert.equal(await page.$("#dev-mode-badge"), null);
  assert.equal(await page.$eval("body", node => node.classList.contains("dev-mode")), true);
  assert.equal(await page.$eval("body", node => node.textContent.includes("仅前端")), false);
  assert.ok((await page.$$("#nav-expert-items .nav-item")).length >= 5);
  assert.match(await page.$eval("#profile-summary-content", node => node.textContent), /C5/);
  assert.match(await page.$eval("#portfolio-content", node => node.textContent), /贵州茅台/);

  await page.evaluate(() => { window.location.hash = "market"; });
  await page.waitForSelector("#market:not([hidden])");
  await page.waitForFunction(
    () => document.querySelector("#market")?.textContent.includes("上证指数"),
  );
  const chartActivity = await page.evaluate(() => {
    const canvas = document.querySelector("#market-kline canvas");
    if (!canvas || !canvas.width || !canvas.height) return null;
    const parseColor = value => {
      const match = value.match(/^#([0-9a-f]{6})$/i);
      return match ? [1, 3, 5].map(index => Number.parseInt(match[1].slice(index - 1, index + 1), 16)) : null;
    };
    const palette = ["--market-up", "--market-down", "--brand"]
      .map(name => parseColor(getComputedStyle(document.body).getPropertyValue(name).trim()))
      .filter(Boolean);
    const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let left = 0;
    let total = 0;
    for (let y = 0; y < canvas.height; y += 2) {
      for (let x = 0; x < canvas.width; x += 2) {
        const offset = (y * canvas.width + x) * 4;
        const matchesPalette = palette.some(([red, green, blue]) =>
          Math.abs(pixels[offset] - red) <= 12
          && Math.abs(pixels[offset + 1] - green) <= 12
          && Math.abs(pixels[offset + 2] - blue) <= 12,
        );
        if (!matchesPalette) continue;
        total += 1;
        if (x < canvas.width / 2) left += 1;
      }
    }
    return {left, total};
  });
  assert.ok(chartActivity, "首次进入市场页面后没有可读取的 K 线画布");
  assert.ok(chartActivity.left > chartActivity.total * 0.3, `K 线仍集中在右侧：${JSON.stringify(chartActivity)}`);

  await page.evaluate(() => { window.location.hash = "copilot"; });
  await page.waitForSelector("#copilot:not([hidden])");
  const healthSnapshot = await page.evaluate(async () => {
    const response = await fetch("/api/v1/advisor/portfolio-health", {method: "POST"});
    return {status: response.status, body: await response.json()};
  });
  assert.equal(healthSnapshot.status, 200);
  assert.equal(healthSnapshot.body.owner_id, "usr-01f9f18ddf81440f80e6b97db526427d");

  const resources = await page.evaluate(() => performance.getEntriesByType("resource").map(entry => entry.name));
  assert.equal(resources.some(url => url.includes("/api/")), false);
  assert.equal(resources.some(url => /127\.0\.0\.1:(8000|8017|8018)/.test(url)), false);
  assert.deepEqual(consoleErrors, []);
  process.stdout.write("Pages snapshot browser checks passed.\n");
} finally {
  await browser.close();
}
