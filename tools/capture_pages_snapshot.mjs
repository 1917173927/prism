import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import puppeteer from "puppeteer-core";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const baseUrl = process.env.PRISM_SNAPSHOT_BASE_URL || "http://127.0.0.1:8018";
const ownerId = process.env.PRISM_SNAPSHOT_OWNER_ID || "usr-01f9f18ddf81440f80e6b97db526427d";
const browserPath = process.env.PRISM_TEST_BROWSER || (
  process.platform === "win32"
    ? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
    : "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
);
const staticIndexPath = path.join(projectRoot, "app", "api", "static", "index.html");
const snapshotPath = path.join(projectRoot, "app", "api", "static", "pages-snapshot.json");

const indexHtml = fs.readFileSync(staticIndexPath, "utf8").replace(
  'value="demo-owner"',
  'value="' + ownerId + '"',
);
const browser = await puppeteer.launch({
  executablePath: browserPath,
  headless: true,
  args: ["--no-sandbox"],
});
const page = await browser.newPage();
const routes = new Map();
const responseTasks = [];

await page.evaluateOnNewDocument(snapshotOwnerId => {
  localStorage.setItem(
    "prism_custom_user_profile_v2",
    JSON.stringify({ownerId: snapshotOwnerId}),
  );
}, ownerId);
await page.setRequestInterception(true);
page.on("request", request => {
  if (request.url().startsWith(baseUrl + "/") && new URL(request.url()).pathname === "/") {
    void request.respond({
      status: 200,
      contentType: "text/html; charset=utf-8",
      body: indexHtml,
    });
    return;
  }
  void request.continue();
});
page.on("response", response => {
  const url = new URL(response.url());
  if (url.origin !== baseUrl || !url.pathname.startsWith("/api/")) return;
  const key = response.request().method().toUpperCase() + " " + url.pathname + url.search;
  responseTasks.push((async () => {
    const body = await response.text();
    const headers = {};
    const contentType = response.headers()["content-type"];
    if (contentType) headers["content-type"] = contentType;
    routes.set(key, {
      status: response.status(),
      headers,
      body,
    });
  })());
});

try {
  await page.goto(baseUrl + "/?snapshot_capture=1", {waitUntil: "networkidle0", timeout: 60000});
  await page.waitForFunction(
    () => !document.body.classList.contains("questionnaire-pending"),
    {timeout: 30000},
  );
  await page.evaluate(() => document.body.classList.add("dev-mode"));
  await new Promise(resolve => setTimeout(resolve, 1500));
  await Promise.all(responseTasks);
} finally {
  await browser.close();
}

if (!routes.has("GET /api/v1/auth/context")) {
  throw new Error("本地页面没有完成账户上下文请求");
}
if (!routes.has("GET /api/v1/advisor/portfolio/current")) {
  throw new Error("本地页面没有完成组合快照请求");
}
if (!routes.has("GET /api/v1/advisor/profile/summary")) {
  throw new Error("本地页面没有完成风险画像请求");
}

const snapshot = {
  schema_version: "prism-pages-snapshot.v1",
  captured_at: new Date().toISOString(),
  source: "local-service",
  owner_id: ownerId,
  routes: Object.fromEntries([...routes].sort(([a], [b]) => a.localeCompare(b))),
};
fs.writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2) + "\n", "utf8");
process.stdout.write(
  "Captured " + routes.size + " local API responses into " + snapshotPath + "\n",
);
