// Runs browser_check.mjs against a local fake site. Needs CHROME_PATH and `npm install` in codelibry-qa/scripts.
// node --test tests/browser_check.test.mjs
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const cf7 = (n, ok) => `<!doctype html><div class="wpcf7"><form>
  <input type="hidden" name="_wpcf7" value="${n}">
  <label>Your name <input name="your-name" required></label><input type="email" name="your-email" required>
  <input name="honeypot" style="display:none"><textarea name="your-message"></textarea>
  <label><input type="checkbox" name="acceptance-gdpr" style="display:none"><span>I accept the privacy policy</span></label>
  <button type="submit">Send</button>
  <div class="wpcf7-response-output"></div></form></div>
<script>document.querySelector('form').addEventListener('submit', async e => {
  e.preventDefault();
  const r = await fetch('/wp-json/contact-form-7/v1/contact-forms/${n}/feedback', { method: 'POST', body: new FormData(e.target) });
  e.target.classList.add(${ok} && r.ok ? 'sent' : 'failed');
  e.target.querySelector('.wpcf7-response-output').textContent = ${ok} ? 'Thank you' : 'There was an error trying to send your message.';
});</script>`;
const NINJA = `<!doctype html><p>Quote</p><div id="nf-form-3-cont" class="nf-form-cont"></div>
<script>setTimeout(() => {
  document.getElementById('nf-form-3-cont').innerHTML = '<form><input name="nf-email" type="email" required><button>Go</button></form>';
  document.querySelector('#nf-form-3-cont form').addEventListener('submit', e => {
    e.preventDefault(); e.target.insertAdjacentHTML('afterend', '<div class="nf-response-msg">Thanks!</div>');
  });
}, 800);</script>`;

// Hostinger-style CDN check: a "Just a moment..." page that sets a cookie and reloads.
const CHALLENGE = `<!doctype html><title>Just a moment...</title><p>Checking your browser before accessing.</p>
<script>setTimeout(() => { document.cookie = 'passed=1; path=/'; location.reload(); }, 1000)</script>`;

const posts = [];
const pages = {
  '/': '<!doctype html><p>Home page with enough text to not count as blank, really.</p><script>throw new Error("boom")</script>',
  '/contact/': cf7(7, true),
  '/broken/': cf7(8, false),
  '/quote/': NINJA,
  '/gate/': cf7(13, true).replace("e.target.classList.add(", "e.target.style.display = 'none'; e.target.classList.add("),
  '/popup/': `<div class="popup" style="opacity:0">${cf7(10, true)}</div>`,
  '/steps/': `<!doctype html><form><input type="hidden" name="_wpcf7" value="11"><input name="budget">
    <button type="button">Next</button><input type="submit" value="Send" style="display:none"></form>`,
};
const server = createServer((req, res) => {
  if (req.method === 'POST') {
    let body = '';
    req.on('data', c => (body += c));
    return req.on('end', () => {
      posts.push(body);
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ status: req.url.includes('/8/') ? 'mail_failed' : 'mail_sent' }));
    });
  }
  if (req.url === '/cdn/') {
    res.setHeader('Content-Type', 'text/html');
    return res.end(/passed=1/.test(req.headers.cookie || '') ? cf7(12, true) : CHALLENGE);
  }
  res.statusCode = pages[req.url] ? 200 : 404;
  res.setHeader('Content-Type', 'text/html');
  res.end(pages[req.url] || 'nope');
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const url = `http://127.0.0.1:${server.address().port}`;
after(() => server.close());

test('renders pages, finds forms by id, submits and reads the result', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'bc-'));
  const file = join(dir, 'config.json');
  writeFileSync(file, JSON.stringify({
    test_data: { name: 'Codelibry QA Test', email: 'qa@example.com', message: '[TEST] please ignore' },
    sites: [{ url: url + '/', forms: [
      { id: 'wpcf7-7', plugin: 'cf7', kind: 'contact', page: url + '/contact/', test: true },
      { id: 'wpcf7-8', plugin: 'cf7', kind: 'contact', page: url + '/broken/', test: true },
      { id: '3', plugin: 'ninja-forms', kind: 'contact', page: url + '/quote/', rendered: 'js', test: true },
      { id: '9', plugin: 'ninja-forms', kind: 'contact', page: url + '/', rendered: 'js', test: true },
      { id: 'wpcf7-13', plugin: 'cf7', kind: 'newsletter', page: url + '/gate/', test: true },
      { id: 'wpcf7-10', plugin: 'cf7', kind: 'newsletter', page: url + '/popup/', test: true },
      { id: 'wpcf7-11', plugin: 'cf7', kind: 'contact', page: url + '/steps/', test: true },
      { id: 'wpcf7-12', plugin: 'cf7', kind: 'contact', page: url + '/cdn/', test: true },
      { id: 'acme/intro', plugin: 'calendly', kind: 'booking', page: url + '/', rendered: 'js', test: true },
    ] }],
  }));
  const stdout = await new Promise((resolve, reject) => execFile('node',
    [new URL('../codelibry-qa/scripts/browser_check.mjs', import.meta.url).pathname, file],
    { env: { ...process.env, HTTPS_PROXY: '' }, timeout: 170000 }, (e, out, err) => e ? reject(new Error(err)) : resolve(out)));
  const r = JSON.parse(stdout);
  const home = r.pages.find(p => p.url === url + '/');
  assert.ok(home.consoleErrors.some(e => e.includes('boom')));
  assert.ok(home.consoleErrors.some(e => e.includes(url + '/favicon.ico')), 'failed resource named');
  assert.equal(home.blank, false);
  const byId = Object.fromEntries(r.forms.map(f => [f.id, f]));
  assert.equal(byId['wpcf7-7'].submit, 'sent');
  assert.equal(byId['wpcf7-7'].message, 'Thank you');
  assert.equal(byId['wpcf7-7'].serverStatus, 'mail_sent');
  assert.equal(byId['wpcf7-8'].submit, 'failed');
  assert.equal(byId['wpcf7-8'].serverStatus, 'mail_failed');
  assert.equal(byId['wpcf7-13'].submit, 'sent', 'form that hides itself on success');
  assert.equal(byId['wpcf7-10'].submit, 'not automated: form hidden on load (popup or closed tab)');
  assert.equal(byId['wpcf7-11'].submit, 'not automated: submit button hidden (multi-step form)');
  assert.equal(r.pages.find(p => p.url === url + '/cdn/').botChallenge, false, 'waited out the CDN check');
  assert.equal(byId['wpcf7-12'].submit, 'sent');
  assert.match(byId['wpcf7-8'].message, /error trying to send/);
  assert.equal(byId['3'].renders, true, 'script-drawn Ninja form found');
  assert.equal(byId['3'].submit, 'sent');
  assert.equal(byId['9'].renders, false, 'missing Ninja form reported');
  assert.equal(byId['acme/intro'].submit, 'not automated: vendor-hosted form in an iframe');
  assert.ok(posts.every(p => p.includes('qa@example.com') && !/name="honeypot"\r\n\r\n\S/.test(p)));
  assert.ok(posts[0].includes('Codelibry QA Test'), 'name field filled from its label');
  assert.ok(posts.every(p => p.includes('name="acceptance-gdpr"')), 'hidden custom consent box ticked');
  assert.equal(posts.length, 4, 'only CF7 #7, #8, #12, #13 post: popup and multi-step forms not submitted');

});
