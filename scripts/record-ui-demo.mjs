/**
 * Records a ~2 minute SupportMemory UI demo (landing → capabilities →
 * architecture → dashboard recovery → KB → receipt).
 *
 * Usage: node scripts/record-ui-demo.mjs
 * Output: demos/supportmemory-ui-demo.webm
 */
import { chromium } from "playwright";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "demos");
const BASE = process.env.DEMO_URL || "http://localhost:3000/hackathon-ui.html";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function slowScroll(page, y, steps = 8) {
  const step = y / steps;
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, step);
    await sleep(180);
  }
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  // Clear prior videos so we can find the new one cleanly
  for (const f of fs.readdirSync(outDir)) {
    if (f.endsWith(".webm") || f.endsWith(".mp4")) {
      try {
        fs.unlinkSync(path.join(outDir, f));
      } catch {}
    }
  }

  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage"],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: outDir,
      size: { width: 1440, height: 900 },
    },
  });

  const page = await context.newPage();
  page.setDefaultTimeout(45000);

  console.log("Opening", BASE);
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await sleep(3500);

  // --- Landing: brand + how it works ---
  console.log("1/6 Landing");
  await slowScroll(page, 1100);
  await sleep(2500);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await sleep(2000);

  // --- Capabilities ---
  console.log("2/6 Capabilities");
  await page.evaluate(() => showPage("capabilities"));
  await sleep(3000);
  await slowScroll(page, 800);
  await sleep(2000);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await sleep(1500);

  // --- Architecture ---
  console.log("3/6 Architecture");
  await page.evaluate(() => showPage("architecture"));
  await sleep(3000);
  await slowScroll(page, 600);
  await sleep(2000);

  // --- Dashboard + recovery demo ---
  console.log("4/6 Dashboard recovery demo");
  await page.evaluate(() => showPage("dashboard"));
  await sleep(3000);

  // Wait for API pill healthy if possible
  try {
    await page.waitForFunction(
      () => {
        const t = document.getElementById("api-pill")?.textContent || "";
        return /online|ok|live|connected/i.test(t) || t.includes("API");
      },
      { timeout: 8000 }
    );
  } catch {}

  await page.evaluate(() => startDemo());
  // Recovery demo can take a bit — hold on dashboard
  await sleep(22000);

  // Composer ask
  console.log("5/6 Composer + KB");
  const composer = page.locator("#composer");
  if (await composer.count()) {
    await composer.click();
    await composer.fill(
      "Customer says SSO still fails after rotating the API key — what should we check next?"
    );
    await sleep(2000);
    await page.evaluate(() => sendComposer());
    await sleep(14000);
  }

  // Knowledge base
  await page.evaluate(() => showPage("knowledge"));
  await sleep(2500);
  await page.evaluate(() => seedKb());
  await sleep(5000);

  const query = page.locator("#kb-query");
  if (await query.count()) {
    await query.fill("API authentication failure SSO");
    await sleep(1200);
    await page.evaluate(() => searchKb());
    await sleep(4500);
  }

  // Back to dashboard + receipt
  console.log("6/6 Receipt + wrap");
  await page.evaluate(() => showPage("dashboard"));
  await sleep(3000);

  const receiptBtn = page.locator("#btn-receipt");
  if (await receiptBtn.count()) {
    const disabled = await receiptBtn.isDisabled();
    if (!disabled) {
      await page.evaluate(() => viewReceipt());
      await sleep(5000);
    } else {
      await sleep(2500);
    }
  }

  await page.evaluate(() => showPage("landing"));
  await sleep(4000);

  const video = page.video();
  await page.close();
  await context.close();
  await browser.close();

  const videoPath = await video.path();
  const finalPath = path.join(outDir, "supportmemory-ui-demo.webm");
  if (videoPath && fs.existsSync(videoPath)) {
    fs.renameSync(videoPath, finalPath);
  }

  const stats = fs.statSync(finalPath);
  console.log("Saved:", finalPath);
  console.log("Size MB:", (stats.size / (1024 * 1024)).toFixed(2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
