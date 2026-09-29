// Preview renders for review: page screenshots at key hours, with the outside services mocked.
// usage: node tools/preview.mjs <outdir> [--quick]
import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';
const require = createRequire(import.meta.url);
let pw; try { pw = require('playwright'); } catch { pw = require('/opt/node22/lib/node_modules/playwright'); }
const out = process.argv[2] || 'tools/out/preview';
mkdirSync(out, { recursive: true });
const BASE = 'http://127.0.0.1:4173/';
const browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

async function context(viewport, dpr, mobile){
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: dpr, isMobile: mobile, hasTouch: mobile,
    locale: 'it-IT', timezoneId: 'Europe/Rome' });
  await ctx.route('https://ipapi.co/**', r => r.fulfill({ json: { city: 'Firenze', country_code: 'IT', latitude: 43.77, longitude: 11.25, timezone: 'Europe/Rome' } }));
  await ctx.route('https://ipwho.is/**', r => r.abort());
  await ctx.route('https://api.open-meteo.com/**', r => r.fulfill({ json: { current: { temperature_2m: 21.4, weather_code: 1, cloud_cover: 18, wind_speed_10m: 3.1 } } }));
  return ctx;
}
export async function shot(ctx, query, file, { unlock = false, clock } = {}){
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(BASE + 'index.html?' + query + (clock ? '&ct=' + clock : ''), { waitUntil: 'load' });
  await page.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 180000 });
  await page.waitForTimeout(1600);
  if (unlock){
    await page.fill('#pw', process.env.BG_PW || '');
    await page.click('#enter');
    await page.waitForTimeout(1400);
  }
  await page.screenshot({ path: file, timeout: 180000 });
  if (errors.length) console.log(file, 'ERRORS:', errors.join(' | '));
  await page.close();
}
const hours = process.argv.includes('--quick') ? [[13, '13:00']] :
  [[6.9, '06:54'], [13, '13:00'], [18.9, '18:54'], [19.45, '19:27'], [20.2, '20:12'], [22.5, '22:30']];
const desk = await context({ width: 1440, height: 900 }, 2, false);
for (const [h, c] of hours) await shot(desk, `hour=${h}&t=20&still`, `${out}/desktop-${c.replace(':', '')}.png`, { clock: c });
if (!process.argv.includes('--quick')){
  await shot(desk, 'hour=20.2&t=20&still', `${out}/desktop-2012-sbloccato.png`, { clock: '20:12', unlock: true });
  const phone = await context({ width: 390, height: 844 }, 3, true);
  for (const [h, c] of [[13, '13:00'], [19.45, '19:27'], [22.5, '22:30']]) await shot(phone, `hour=${h}&t=20&still`, `${out}/telefono-${c.replace(':', '')}.png`, { clock: c });
}
await browser.close();
