// Renders screenshots of the scene or the page with headless Chromium (WebGL2 via SwiftShader).
// usage: node tools/shoot.mjs <url-path> <out.png> [width height dpr] [--wait ms]
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
let pw; try { pw = require('playwright'); } catch { pw = require('/opt/node22/lib/node_modules/playwright'); }
const { chromium } = pw;
const [,, path, out, w = '1440', h = '900', dpr = '1'] = process.argv;
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: +dpr });
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://127.0.0.1:4173/' + path, { waitUntil: 'load' });
await page.waitForFunction(() => document.body.dataset.ready === '1' || !location.search.includes('still'), null, { timeout: 120000 });
await page.waitForTimeout(path.includes('still') ? 300 : 2500);
await page.screenshot({ path: out, timeout: 120000 });
if (errors.length) console.log('ERRORS:', errors.join('\n'));
await browser.close();
