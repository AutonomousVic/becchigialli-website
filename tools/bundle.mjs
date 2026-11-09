// Builds ONE self-contained HTML file from the site: fonts and images become data: URIs, astro.js
// and content.json are inlined, and the scene's source goes at the very end of the page, from where
// index.html puts it into the frame (srcdoc) once the panel has been drawn.
// Useful wherever the page cannot load sibling files (a preview, an artifact, an e-mail attachment).
//   node tools/bundle.mjs [out.html]              a complete document, opens anywhere
//   node tools/bundle.mjs --fragment [out.html]   no doctype/html/head/body, for hosts that wrap the page themselves
//   --title "Name"                                replaces the <title> (fragment: no dash or explainer)
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const fragment = args.includes('--fragment');
const ti = args.indexOf('--title');
const title = ti >= 0 ? args[ti + 1] : null;
const out = args.find((a, i) => !a.startsWith('--') && !(ti >= 0 && i === ti + 1)) || join(root, 'dist', fragment ? 'becchigialli-fragment.html' : 'becchigialli-single.html');

const read = f => readFileSync(join(root, f), 'utf8');
const MIME = { '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2' };
const dataUri = f => `data:${MIME[extname(f)]};base64,${readFileSync(join(root, f)).toString('base64')}`;
const must = (cond, msg) => { if (!cond) throw new Error('bundle: ' + msg); };

// the scene: every 'img/...' it loads becomes a data: URI
let scene = read('scene.html');
let n = 0;
scene = scene.replace(/'(img\/[\w.-]+)'/g, (_, f) => { n++; return `'${dataUri(f)}'`; });
must(n >= 9, `expected at least 9 images in scene.html, found ${n}`);
// it travels inside a <script type="text/plain">: nothing in it may end or re-open a script there
must(!/<\\(\/?script|!--)/i.test(scene), 'scene.html already contains an escaped script tag');
const sceneText = scene.replace(/<(\/?script|!--)/gi, '<\\$1');

let page = read('index.html');
page = page.replace(/<link rel="preload"[^>]*>\n?/g, '');
let nf = 0;
page = page.replace(/url\((fonts\/[\w.-]+)\)/g, (_, f) => { nf++; return `url(${dataUri(f)})`; });
must(nf >= 7, `expected 7 fonts, found ${nf}`);
let ni = 0;
page = page.replace(/url\((img\/[\w.-]+)\)/g, (_, f) => { ni++; return `url(${dataUri(f)})`; });
must(ni >= 1, 'the poster is gone from index.html');

// astro.js: same code, wrapped so its names cannot meet the page's
const astro = read('astro.js').replace(/^export /gm, '');
const importLine = "import { sunTimes, OFFICES } from './astro.js';";
must(page.includes(importLine), 'the import of astro.js is gone from index.html');
page = page.replace(importLine, `const { sunTimes, OFFICES } = (() => {\n${astro}\nreturn { sunTimes, OFFICES };\n})();`);

// the scene frame starts empty; its source goes last
const frameTag = '<iframe id="scene-frame" src="scene.html"';
must(page.includes(frameTag), 'the scene iframe is gone from index.html');
must(page.includes("getElementById('scene-src')"), 'index.html no longer picks up the scene source');
page = page.replace(frameTag, '<iframe id="scene-frame"');

// the content behind the password
const content = JSON.stringify(JSON.parse(read('content.json'))).replace(/<\//g, '<\\/');
page = page.replace('<script type="module">', `<script type="application/json" id="content-inline">${content}</script>\n<script type="module">`);

// the page's own script runs as soon as the parser reaches it (a module would wait for the whole
// file, the scene's source included, before the lock even answers): same code, in its own scope
const modOpen = '<script type="module">', ma = page.indexOf(modOpen), mz = page.indexOf('</script>', ma);
must(ma >= 0 && mz > ma, 'the page script is gone from index.html');
must(!/\bawait\b[^\n]*$/m.test(page.slice(ma, mz).split('\n').filter(l => /^\S/.test(l)).join('\n')), 'top-level await in the page script');
page = page.slice(0, ma) + "<script>\n(() => {\n'use strict';\n" + page.slice(ma + modOpen.length, mz) + '})();\n' + page.slice(mz);

if (title) page = page.replace(/<title>[^<]*<\/title>/, `<title>${title}</title>`);

if (fragment){
  page = page
    .replace(/<!DOCTYPE html>\s*/i, '')
    .replace(/<\/?html[^>]*>\s*/g, '')
    .replace(/<\/?head>\s*/g, '')
    .replace(/<\/?body>\s*/g, '')
    .replace(/<meta charset[^>]*>\s*/, '')
    .replace(/<meta name="viewport"[^>]*>\s*/, '')
    .replace(/<meta name="theme-color"[^>]*>\s*/, '')
    .replace(/<meta name="description"[^>]*>\s*/, '')
    .replace(/<link rel="icon"[^>]*>\s*/, '');
}
// last of all, so nothing above touches the scene's own tags
const tail = `<script type="text/plain" id="scene-src">${sceneText}</script>\n`;
page = page.includes('</body>') ? page.replace('</body>', () => tail + '</body>') : page.trimEnd() + '\n' + tail;
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, page);
console.log(`${out}: ${(page.length / 1048576).toFixed(2)} MB (${n} images in the scene, ${nf} fonts)`);
