/**
 * Records a ~2 minute SupportMemory UI demo.
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

async function slowScroll(page, y, steps = 6) {
  const step = y / steps;
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, step);
    await sleep(120);
  }
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
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
  page.setDefaultTimeout(60000);

  console.log("Opening", BASE);
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await sleep(2000);

  // Landing (~12s)
  console.log("1/6 Landing");
  await slowScroll(page, 700);
  await sleep(1500);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await sleep(800);

  // Capabilities (~10s)
  console.log("2/6 Capabilities");
  await page.evaluate(() => showPage("capabilities"));
  await sleep(1800);
  await slowScroll(page, 500);
  await sleep(1000);

  // Architecture (~8s)
  console.log("3/6 Architecture");
  await page.evaluate(() => showPage("architecture"));
  await sleep(1800);
  await slowScroll(page, 400);
  await sleep(900);

  // Dashboard recovery (~45s total including API)
  console.log("4/6 Dashboard recovery demo");
  await page.evaluate(() => showPage("dashboard"));
  await sleep(1500);

  const demoDone = page
    .waitForFunction(
      () => {
        const s = (document.getElementById("sys-state")?.textContent || "").toUpperCase();
        return s.includes("RECOVER") || s.includes("ACTIVE");
      },
      { timeout: 55000 }
    )
    .catch(() => null);

  await page.evaluate(() => startDemo());
  await demoDone;
  await sleep(4000);

  // Composer (~20s)
  console.log("5/6 Composer + KB");
  const composer = page.locator("#composer");
  if (await composer.count()) {
    await composer.click();
    await composer.fill(
      "Customer says SSO still fails after rotating the API key — what should we check next?"
    );
    await sleep(1000);
    const replyWait = page
      .waitForFunction(
        () => {
          const t = document.getElementById("thread")?.textContent || "";
          return t.length > 200;
        },
        { timeout: 25000 }
      )
      .catch(() => null);
    await page.evaluate(() => sendComposer());
    await replyWait;
    await sleep(2500);
  }

  // Knowledge base (~18s)
  await page.evaluate(() => showPage("knowledge"));
  await sleep(1200);
  await page.evaluate(() => seedKb());
  await sleep(3500);

  const query = page.locator("#kb-query");
  if (await query.count()) {
    await query.fill("API authentication failure SSO");
    await sleep(600);
    await page.evaluate(() => searchKb());
    await sleep(3000);
  }

  // Wrap (~12s)
  console.log("6/6 Receipt + wrap");
  await page.evaluate(() => showPage("dashboard"));
  await sleep(1500);

  const receiptBtn = page.locator("#btn-receipt");
  if (await receiptBtn.count()) {
    const disabled = await receiptBtn.isDisabled();
    if (!disabled) {
      await page.evaluate(() => viewReceipt());
      await sleep(2500);
    }
  }

  await page.evaluate(() => showPage("landing"));
  await sleep(2000);

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
