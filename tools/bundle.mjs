// Builds ONE self-contained HTML file from the site: fonts and images become data: URIs, astro.js
// and content.json are inlined, and the scene goes into the page as an iframe srcdoc.
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
const out = args.find((a, i) => !a.startsWith('--') && i !== ti + 1) || join(root, 'dist', fragment ? 'becchigialli-fragment.html' : 'becchigialli-single.html');

const read = f => readFileSync(join(root, f), 'utf8');
const MIME = { '.jpg': 'image/jpeg', '.png': 'image/png', '.woff2': 'font/woff2' };
const dataUri = f => `data:${MIME[extname(f)]};base64,${readFileSync(join(root, f)).toString('base64')}`;
const must = (cond, msg) => { if (!cond) throw new Error('bundle: ' + msg); };

// the scene: every 'img/...' it loads becomes a data: URI
let scene = read('scene.html');
let n = 0;
scene = scene.replace(/'(img\/[\w.-]+)'/g, (_, f) => { n++; return `'${dataUri(f)}'`; });
must(n >= 7, `expected at least 7 images in scene.html, found ${n}`);
const attr = s => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;');

let page = read('index.html');
page = page.replace(/<link rel="preload"[^>]*>\n?/, '');
let nf = 0;
page = page.replace(/url\((fonts\/[\w.-]+)\)/g, (_, f) => { nf++; return `url(${dataUri(f)})`; });
must(nf >= 7, `expected 7 fonts, found ${nf}`);

// astro.js: same code, wrapped so its names cannot meet the page's
const astro = read('astro.js').replace(/^export /gm, '');
const importLine = "import { sunTimes, OFFICES } from './astro.js';";
must(page.includes(importLine), 'the import of astro.js is gone from index.html');
page = page.replace(importLine, `const { sunTimes, OFFICES } = (() => {\n${astro}\nreturn { sunTimes, OFFICES };\n})();`);

// the scene frame
const frameTag = '<iframe id="scene-frame" src="scene.html"';
must(page.includes(frameTag), 'the scene iframe is gone from index.html');
page = page.replace(frameTag, `<iframe id="scene-frame" srcdoc="${attr(scene)}"`);

// the content behind the password
const content = JSON.stringify(JSON.parse(read('content.json'))).replace(/<\//g, '<\\/');
page = page.replace('<script type="module">', `<script type="application/json" id="content-inline">${content}</script>\n<script type="module">`);

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
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, page);
console.log(`${out}: ${(page.length / 1048576).toFixed(2)} MB (${n} images in the scene, ${nf} fonts)`);
