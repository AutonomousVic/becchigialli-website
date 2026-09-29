// Writes the fingerprint of the site password into index.html (the password itself is never stored).
// usage: node tools/set-password.mjs 'the password'
// The check is scenographic: anyone can still open content.json. Do not reuse a real password.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash, randomBytes } from 'node:crypto';
const pw = process.argv[2];
if (!pw) { console.error("usage: node tools/set-password.mjs 'password'"); process.exit(1); }
const salt = randomBytes(12).toString('base64url');
const hash = createHash('sha256').update(salt + '\n' + pw.trim().normalize('NFC')).digest('hex');
const file = new URL('../index.html', import.meta.url);
const html = readFileSync(file, 'utf8');
const tag = `<meta name="bg-auth" content="v1;salt=${salt};sha256=${hash}">`;
if (!/<meta name="bg-auth"[^>]*>/.test(html)) { console.error('bg-auth meta tag not found'); process.exit(1); }
writeFileSync(file, html.replace(/<meta name="bg-auth"[^>]*>/, tag));
console.log('password fingerprint updated');
