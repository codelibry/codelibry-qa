#!/usr/bin/env node
// Headless-browser half of the check: rendering, console errors, forms (incl. script-drawn ones),
// and test submissions. Prints one JSON line per site.
// Usage: node browser_check.mjs <config.json> [site-url ...]
// config.json is the chat's codelibry-qa config block. Env: CHROME_PATH, HTTPS_PROXY / NO_PROXY.
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright-core';

const SUCCESS = [
  '.wpcf7 form.sent', '.gform_confirmation_message', '.wpforms-confirmation-container', '.wpforms-confirmation-container-full',
  '.elementor-message-success', '.nf-response-msg', '.submitted-message', '.hsfc-PostSubmit', '._form-thank-you', '.forminator-success',
  '.ff-message-success',
].join(', ');
const FAILURE = [
  '.wpcf7 form.invalid', '.wpcf7 form.unaccepted', '.wpcf7 form.spam', '.wpcf7 form.failed', '.wpcf7 form.aborted',
  '.gform_validation_errors', '.validation_error', '.wpforms-error-container', 'label.wpforms-error', '.elementor-message-danger',
  '.nf-error-msg', '.hs-error-msgs', '.hsfc-ErrorAlert', '.forminator-error', '.ff-errors-in-stack',
].join(', ');
// Vendor-hosted forms live in a cross-site iframe: checked for rendering, submitted by hand.
const IFRAME_VENDORS = {
  typeform: id => `[data-tf-widget="${id}"] iframe, iframe[src*="typeform.com/to/${id}"]`,
  jotform: id => `iframe[src*="${id}"], iframe[id="JotFormIFrame-${id}"]`,
  'google-forms': id => `iframe[src*="${id}"]`,
  tally: id => `iframe[src*="tally.so/embed/${id}"]`,
  cognito: () => 'iframe[src*="cognitoforms"], .cog-form',
  'zoho-forms': id => `iframe[src*="${id}"]`,
  pipedrive: () => 'iframe[src*="pipedrive"]',
  'ms-forms': () => 'iframe[src*="forms.office.com"]',
  calendly: () => '.calendly-inline-widget iframe',
};
const NEVER_SUBMIT = new Set(['search', 'login', 'comment', 'shop', 'booking']);
const CONSENT = /accept|consent|gdpr|privacy|terms|agree|policy/;
const CHALLENGE = /checking your browser|just a moment|verify you are human|attention required|ddos protection/i;
const CAP = 10;

const [configPath, ...only] = process.argv.slice(2);
if (!configPath) {
  console.error('usage: node browser_check.mjs <config.json> [site-url ...]');
  process.exit(2);
}
const config = JSON.parse(readFileSync(configPath, 'utf8'));
const test = config.test_data || {};
const proxy = proxyFromEnv();
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined, args: ['--disable-gpu'], proxy });
const ua = `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${browser.version()} Safari/537.36`;

for (const site of config.sites.filter(s => !only.length || only.includes(s.url))) {
  const out = await checkSite(site).catch(e => ({ site: site.url, error: String(e.message || e).split('\n')[0].slice(0, 300) }));
  console.log(JSON.stringify(out));
}
await browser.close();

function proxyFromEnv() {
  const raw = process.env.HTTPS_PROXY || process.env.https_proxy;
  if (!raw) return undefined;
  const u = new URL(raw);
  return {
    server: `${u.protocol}//${u.host}`,
    username: decodeURIComponent(u.username) || undefined,
    password: decodeURIComponent(u.password) || undefined,
    bypass: process.env.NO_PROXY || process.env.no_proxy || undefined,
  };
}

async function checkSite(site) {
  const context = await browser.newContext({ userAgent: ua, viewport: { width: 1440, height: 900 } });
  const out = { site: site.url, checkedAt: new Date().toISOString(), pages: [], forms: [] };
  try {
    const pages = [...new Set([site.url, ...(site.forms || []).map(f => f.page)])];
    for (const url of pages) out.pages.push(await checkPage(context, url, (site.forms || []).filter(f => f.page === url)));
    out.forms = out.pages.flatMap(p => p.forms);
    for (const p of out.pages) delete p.forms;
  } finally {
    await context.close();
  }
  return out;
}

async function checkPage(context, url, forms) {
  const page = await context.newPage();
  const consoleErrors = [];
  const push = t => consoleErrors.length < CAP && consoleErrors.push(t.slice(0, 300));
  // "Failed to load resource" doesn't name the file; its location does.
  page.on('console', m => m.type() === 'error' && push(/^Failed to load resource/.test(m.text()) ? `${m.text()}: ${m.location().url}` : m.text()));
  page.on('pageerror', e => push(`pageerror: ${e.message}`));
  const r = { url, status: null, forms: [] };
  try {
    let res = await page.goto(url, { waitUntil: 'load', timeout: 45000 });
    // CDN bot protection often refuses the first hit and sets a cookie.
    if ([403, 429, 503].includes(res?.status())) {
      r.firstStatus = res.status();
      await page.waitForTimeout(3000);
      consoleErrors.length = 0;
      res = await page.goto(url, { waitUntil: 'load', timeout: 45000 });
    }
    // CDN bot checks (Hostinger, Cloudflare) show a "Checking your browser" page that reloads itself once passed.
    const until = Date.now() + 20000;
    while (CHALLENGE.test(await page.title().catch(() => '')) && Date.now() < until) {
      await page.waitForEvent('load', { timeout: Math.max(1, until - Date.now()) }).catch(() => {});
    }
    r.botChallenge = CHALLENGE.test(await page.title().catch(() => ''));
    r.status = res?.status() ?? null;
    r.finalUrl = page.url();
    r.offOrigin = new URL(page.url()).hostname.replace(/^www\./, '') !== new URL(url).hostname.replace(/^www\./, '');
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {}); // script-drawn forms
    r.blank = await page.evaluate(() => (document.body?.innerText || '').trim().length < 50 && !document.querySelector('img, video, canvas'));
    for (const f of forms) {
      r.forms.push(r.botChallenge ? { id: f.id, plugin: f.plugin, kind: f.kind, page: f.page, submit: 'not checked: CDN bot challenge did not pass' }
        : await checkForm(page, f));
    }
  } catch (e) {
    r.error = String(e.message).split('\n')[0].slice(0, 300);
  }
  r.consoleErrors = consoleErrors;
  await page.close();
  return r;
}

function selectorFor(f) {
  if (f.selector) return f.selector;
  const id = String(f.id || '');
  let m;
  if ((m = id.match(/^wpcf7-(\d+)$/))) return `form:has(input[name="_wpcf7"][value="${m[1]}"])`;
  if ((m = id.match(/^gform_submit-(\d+)$/))) return `#gform_${m[1]}`;
  if ((m = id.match(/^wpforms-(\d+)$/))) return `#wpforms-form-${m[1]}`;
  if ((m = id.match(/^form_id-(.+)$/))) return `form:has(input[name="form_id"][value="${m[1]}"])`;
  if (f.plugin === 'ninja-forms') return `#nf-form-${id}-cont form`;
  if (f.plugin === 'hubspot') return `form[data-form-id="${id}"], form[id^="hsForm_${id}"]`;
  if (f.plugin === 'klaviyo') return `.klaviyo-form-${id} form`;
  if (f.plugin === 'activecampaign') return `form._form_${id}`;
  return `[id="${id}"]`;
}

// Searches the page and its iframes (HubSpot can sit in one); returns the first visible (or, with attached, present) match.
async function locate(page, selector, timeout = 15000, attached = false) {
  const until = Date.now() + timeout;
  do {
    for (const frame of page.frames()) {
      const loc = frame.locator(selector).first();
      if (await (attached ? loc.count() : loc.isVisible()).catch(() => false)) return { frame, loc };
    }
    await page.waitForTimeout(500);
  } while (Date.now() < until);
  return null;
}

// isVisible() ignores opacity, so a form in a closed popup (opacity 0 wrapper) would pass it.
function shown(loc) {
  return loc.evaluate(e => e.checkVisibility({ opacityProperty: true, visibilityProperty: true })).catch(() => false);
}

async function checkForm(page, f) {
  const r = { id: f.id, plugin: f.plugin, kind: f.kind, page: f.page };
  try {
    if (IFRAME_VENDORS[f.plugin]) {
      r.renders = !!(await locate(page, IFRAME_VENDORS[f.plugin](f.id)));
      r.submit = 'not automated: vendor-hosted form in an iframe';
      return r;
    }
    const found = await locate(page, selectorFor(f), 15000, true);
    r.renders = !!found;
    if (!found) return { ...r, submit: 'form not found or not drawn' };
    if (!(await shown(found.loc))) return { ...r, submit: 'not automated: form hidden on load (popup or closed tab)' };
    const buttons = await found.loc.locator('[type=submit], button:not([type]), .hs-button').all();
    let button = null;
    for (const b of buttons) if (!button && await shown(b)) button = b;
    if (buttons.length && !button) return { ...r, submit: 'not automated: submit button hidden (multi-step form)' };
    if (f.test === false || NEVER_SUBMIT.has(f.kind)) return { ...r, submit: 'not tested (by config)' };
    if (!test.email) return { ...r, submit: 'not tested: no test_data in config' };

    r.skippedFields = await fill(found.loc, new URL(f.page).origin);
    if (r.skippedFields.includes('file (required)')) return { ...r, submit: 'skipped: required file upload' };
    // CF7's REST reply is the result: it tells a mail failure from spam, and some forms hide themselves on success.
    let feedback = null, pending = null;
    const onResponse = res => {
      if (/contact-form-7\/v1\/contact-forms\/\d+\/feedback/.test(res.url())) pending = res.json().then(j => { feedback = j; }, () => {});
    };
    page.on('response', onResponse);
    const before = page.url();
    if (button) await button.click({ timeout: 5000 });
    else await found.loc.evaluate(el => el.requestSubmit());

    r.submit = 'no result in 30s';
    for (const until = Date.now() + 30000; Date.now() < until;) {
      if (page.url() !== before) { r.submit = 'sent (redirected)'; break; }
      if (feedback?.status) {
        r.serverStatus = feedback.status;
        r.submit = feedback.status === 'mail_sent' ? 'sent' : 'failed';
        r.message = String(feedback.message || '').slice(0, 300) || null;
        break;
      }
      if (page.frames().some(fr => /recaptcha\/api2\/bframe|hcaptcha\.com.*challenge/.test(fr.url()))
        && await page.locator('iframe[src*="bframe"], iframe[src*="hcaptcha"][title*="challenge" i]').first().isVisible().catch(() => false)) {
        r.submit = 'captcha challenge: needs a human'; break;
      }
      const hit = await locate(page, `${SUCCESS}, ${FAILURE}`, 0);
      if (hit) {
        r.submit = await hit.loc.evaluate((el, s) => el.matches(s) ? 'sent' : 'failed', SUCCESS);
        r.message = (await hit.loc.innerText().catch(() => '')).trim().slice(0, 300) || null;
        break;
      }
      await page.waitForTimeout(500);
    }
    page.off('response', onResponse);
    if (pending) await Promise.race([pending, page.waitForTimeout(5000)]);
    if (feedback?.status && !r.serverStatus) r.serverStatus = feedback.status;
    const cf7 = await found.frame.locator('.wpcf7-response-output').first().innerText({ timeout: 500 }).catch(() => '');
    if (cf7.trim()) r.message = cf7.trim().slice(0, 300);
    r.finalUrl = page.url();
  } catch (e) {
    r.error = String(e.message).split('\n')[0].slice(0, 300);
  }
  return r;
}

// Fills visible fields from test_data by what each field asks for. Returns fields it could not fill.
async function fill(form, siteUrl) {
  const skipped = [];
  const radios = new Set();
  for (const el of await form.locator('input, textarea, select').all()) {
    const visible = await el.isVisible().catch(() => false);
    const f = await el.evaluate(e => ({
      tag: e.tagName.toLowerCase(), type: (e.type || '').toLowerCase(), name: e.name || e.id || '', value: e.value,
      required: e.required || e.getAttribute('aria-required') === 'true',
      hint: [e.name, e.id, e.placeholder, e.getAttribute('aria-label'), e.autocomplete,
        e.labels?.[0]?.innerText, e.closest('label')?.innerText].filter(Boolean).join(' ').toLowerCase(),
    }));
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(f.type)) continue;
    if (f.type === 'checkbox') {
      // Custom-styled consent boxes hide the real input; a DOM click ticks it and fires change.
      if (f.required || CONSENT.test(f.hint)) {
        await (visible ? el.check() : el.evaluate(e => e.checked || e.click())).catch(() => skipped.push(f.name));
      }
      continue;
    }
    if (!visible) continue; // honeypots are hidden
    if (f.type === 'file') { if (f.required) skipped.push('file (required)'); continue; }
    if (f.type === 'radio') {
      if (!radios.has(f.name)) { radios.add(f.name); await el.check().catch(() => skipped.push(f.name)); }
      continue;
    }
    if (f.tag === 'select') {
      if (!f.value) {
        const v = await el.evaluate(e => [...e.options].find(o => o.value && !o.disabled)?.value);
        if (v) await el.selectOption(v); else if (f.required) skipped.push(f.name);
      }
      continue;
    }
    if (f.value) continue;
    const date = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
    const value =
      f.type === 'email' || /e-?mail/.test(f.hint) ? test.email
      : f.type === 'tel' || /phone|tel|mobile/.test(f.hint) ? test.phone || '+10000000000'
      : f.type === 'url' || /website|url/.test(f.hint) ? siteUrl
      : f.type === 'number' ? '1'
      : f.type === 'date' ? date
      : f.tag === 'textarea' || /message|comment|enquiry|inquiry|details/.test(f.hint) ? test.message
      : /company|organi[sz]ation|business/.test(f.hint) ? test.company || 'Test'
      : /name/.test(f.hint) ? test.name
      : 'Test';
    await el.fill(String(value ?? 'Test')).catch(() => skipped.push(f.name));
  }
  return skipped;
}
