const puppeteer = require("puppeteer-core");
const path = require("path");
const fs = require("fs");

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const OUTPUT_DIR = path.resolve(__dirname, "../docs/showcase");
const BASE_URL = "http://127.0.0.1:8000";

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

(async () => {
  console.log("[Showcase] Launching Chrome...");
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--hide-scrollbars"],
    defaultViewport: { width: 1600, height: 1050, deviceScaleFactor: 2 },
  });

  const page = await browser.newPage();

  // Helper to save screenshot with notification
  async function takeScreenshot(name, clip = null, fullPage = false) {
    const filePath = path.join(OUTPUT_DIR, name);
    const opts = { path: filePath };
    if (fullPage) opts.fullPage = true;
    else if (clip) opts.clip = clip;
    await page.screenshot(opts);
    console.log(`[Showcase] Saved: ${name}`);
  }

  try {
    // 1. Investor Workbench Overview
    console.log("[Showcase] 1. Loading Investor Workbench Overview...");
    await page.goto(`${BASE_URL}/#copilot`, { waitUntil: "networkidle0" });
    await sleep(1500);
    await takeScreenshot("01_v3_investor_workbench_overview.png");

    // 2. Portfolio Health Check Execution
    console.log("[Showcase] 2. Running Portfolio Health Check...");
    await page.click("#copilot-btn-health-check");
    await sleep(2500); // wait for analysis computation & DOM rendering
    // Scroll down slightly to center the output
    await page.evaluate(() => {
      const el = document.getElementById("copilot-decision-output");
      if (el) el.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await sleep(500);
    await takeScreenshot("02_v3_health_check_result.png");

    // 3. Stock Deep Research (300750)
    console.log("[Showcase] 3. Running Stock Deep Research (300750)...");
    await page.evaluate(() => {
      window.scrollTo(0, 0);
    });
    await sleep(500);
    await page.click("#copilot-btn-stock-research");
    await sleep(2500);
    await page.evaluate(() => {
      const el = document.getElementById("copilot-decision-output");
      if (el) el.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await sleep(500);
    await takeScreenshot("03_v3_stock_deep_research.png");

    // 4. Rebalancing Plan Execution
    console.log("[Showcase] 4. Running Rebalancing Plan Generation...");
    await page.evaluate(() => {
      window.scrollTo(0, 0);
    });
    await sleep(500);
    await page.click("#copilot-btn-rebalance");
    await sleep(2500);
    await page.evaluate(() => {
      const el = document.getElementById("copilot-decision-output");
      if (el) el.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await sleep(500);
    await takeScreenshot("04_v3_rebalancing_plan_stepper.png");

    // 5. Portfolio Natural Input Modal
    console.log("[Showcase] 5. Opening Portfolio Modal...");
    await page.evaluate(() => {
      window.scrollTo(0, 0);
    });
    await sleep(300);
    await page.click("#open-portfolio-modal-btn");
    await sleep(800);
    await takeScreenshot("05_v3_portfolio_input_modal.png");
    await page.click("#close-portfolio-modal-btn");
    await sleep(500);

    // 6. User Profile Customization Modal
    console.log("[Showcase] 6. Opening Profile Modal...");
    await page.click("#open-profile-modal-btn");
    await sleep(800);
    await takeScreenshot("06_v3_user_profile_modal.png");
    await page.click("#close-profile-modal-btn");
    await sleep(500);

    // 7. Advanced Explainability DAG & Drivers
    console.log("[Showcase] 7. Running Advanced Explainability...");
    await page.goto(`${BASE_URL}/#advanced-explainability`, { waitUntil: "networkidle0" });
    await sleep(1000);
    await page.click("#run-explainability");
    await sleep(2500);
    await page.evaluate(() => {
      const el = document.getElementById("advanced-explainability");
      if (el) el.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await sleep(500);
    await takeScreenshot("07_v2_advanced_explainability_dag.png");

    // 8. Scenario Simulation Diff & Invalidation
    console.log("[Showcase] 8. Running Scenario Simulation...");
    await page.goto(`${BASE_URL}/#scenario-simulation`, { waitUntil: "networkidle0" });
    await sleep(1000);
    await page.click("#run-scenario-simulation");
    await sleep(2500);
    await page.evaluate(() => {
      const el = document.getElementById("scenario-simulation");
      if (el) el.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await sleep(500);
    await takeScreenshot("08_v2_scenario_simulation_diff.png");

    // 9. Automated Evaluation Dashboard Scorecard (in Developer Mode)
    console.log("[Showcase] 9. Running Evaluation Dashboard in Developer Mode...");
    await page.goto(`${BASE_URL}/?dev=1#evaluation-dashboard`, { waitUntil: "networkidle0" });
    await sleep(1500);
    await page.evaluate(() => {
      const btn = document.getElementById("run-evaluation-suite");
      if (btn) {
        btn.scrollIntoView();
        btn.click();
      }
    });
    await sleep(3500);
    await page.evaluate(() => {
      const el = document.getElementById("evaluation-dashboard");
      if (el) el.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await sleep(500);
    await takeScreenshot("09_v2_evaluation_dashboard_scorecard.png");

    // 10. Developer Mode Four-Track Research Matrix (V1 Architecture)
    console.log("[Showcase] 10. Running Research Matrix (V1 Architecture)...");
    await page.goto(`${BASE_URL}/?dev=1#research-matrix`, { waitUntil: "networkidle0" });
    await sleep(1500);
    await page.evaluate(() => {
      const btn = document.getElementById("run-research-matrix");
      if (btn) {
        btn.scrollIntoView();
        btn.click();
      }
    });
    await sleep(3000);
    await page.evaluate(() => {
      const el = document.getElementById("research-matrix");
      if (el) el.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await sleep(500);
    await takeScreenshot("11_v1_developer_research_matrix.png");

    // 11. Backend OpenAPI Swagger Architecture
    console.log("[Showcase] 11. Capturing Backend Swagger Architecture...");
    await page.goto(`${BASE_URL}/api/docs`, { waitUntil: "networkidle0" });
    await sleep(1500);
    await takeScreenshot("10_backend_api_architecture_swagger.png", null, true);

    console.log("[Showcase] All screenshots captured successfully!");
  } catch (err) {
    console.error("[Showcase] Error capturing screenshots:", err);
  } finally {
    await browser.close();
  }
})();
