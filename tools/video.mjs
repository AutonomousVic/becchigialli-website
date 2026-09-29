// Records a short preview video of the page: frames rendered deterministically, encoded to MP4.
// usage: FFMPEG=/path/to/ffmpeg node tools/video.mjs out.mp4 [width height]
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
const require = createRequire(import.meta.url);
let pw; try { pw = require('playwright'); } catch { pw = require('/opt/node22/lib/node_modules/playwright'); }
const [,, out = 'preview.mp4', w = '960', h = '600'] = process.argv;
const FPS = 24;
// [label, seconds, hour at start, hour at end, wind m/s]
const CLIPS = process.env.CLIPS ? JSON.parse(process.env.CLIPS) :
  [['giorno, poco vento', 6, 13, 13, 2], ['giorno, vento forte', 6, 13, 13, 14], ['sera', 6, 20.35, 20.35, 4]];
const browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const ctx = await browser.newContext({ viewport: { width: +w, height: +h }, deviceScaleFactor: 1, locale: 'it-IT', timezoneId: 'Europe/Rome' });
await ctx.route('https://ipapi.co/**', r => r.fulfill({ json: { city: 'Firenze', country_code: 'IT', latitude: 43.77, longitude: 11.25, timezone: 'Europe/Rome' } }));
await ctx.route('https://ipwho.is/**', r => r.abort());
await ctx.route('https://api.open-meteo.com/**', r => r.fulfill({ json: { current: { temperature_2m: 21.4, weather_code: 1, cloud_cover: 18, wind_speed_10m: 3.1 } } }));
const page = await ctx.newPage();
await page.goto('http://127.0.0.1:4173/index.html?hour=13&t=0&still', { waitUntil: 'load' });
await page.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 180000 });
await page.waitForTimeout(1200);
const scene = page.frames().find(f => f.url().includes('scene.html'));
const ff = spawn(process.env.FFMPEG || 'ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', String(FPS), '-i', '-',
  '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'slow', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
let t = 30;
for (const [label, secs, h0, h1, wind = 3] of CLIPS){
  const n = secs*FPS;
  for (let i = 0; i < n; i++){
    const hour = h0 + (h1 - h0)*i/Math.max(1, n - 1);
    await page.evaluate(hh => { document.getElementById('clock').textContent =
      String(Math.floor(hh)).padStart(2, '0') + ':' + String(Math.floor((hh % 1)*60)).padStart(2, '0'); }, hour);
    await scene.evaluate(([hh, tt, ww]) => window.__scene.set(hh, tt, ww), [hour, t, wind]);
    ff.stdin.write(await page.screenshot({ type: 'jpeg', quality: 92 }));
    t += 1/FPS;
  }
  console.log('clip', label, 'done');
}
ff.stdin.end();
await new Promise(r => ff.on('close', r));
await browser.close();
