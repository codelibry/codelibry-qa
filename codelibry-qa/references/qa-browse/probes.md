# qa-browse — Probe Library

Runnable Playwright snippets for the `qa-browse` skill. Every one of these was written against a
real bug and is phrased to adapt: swap the selectors for whatever the Step 0 detection found.

All snippets are bodies for `browser_run_code_unsafe`, which receives `page`. Prefer one snippet
doing ten steps over ten tool calls — and it is the only path to trusted `page.mouse.wheel` input
and to per-breakpoint `BrowserContext`s.

Each probe states **what it proves** and **its false-positive rule**. Skipping the false-positive
rule is how a QA pass produces a confident wrong report.

---

## 0. Ground rules that make readings trustworthy

| Rule | Why |
|---|---|
| Scroll with `page.mouse.wheel`, never `scrollTo` / `scrollIntoView` | Smooth-scroll libraries (ScrollSmoother, Lenis) move content by transform and keep their own virtual position. A programmatic scroll desyncs it and every later reading is garbage — including `window.scrollY`, which can read `0` while the page visually sits mid-document. |
| Settle before asserting | 1.5–2 s after reaching a section. A tween in progress reads as a partial opacity and looks exactly like a bug. |
| One `BrowserContext` per breakpoint / emulation | Viewport, `hasTouch`, `isMobile`, `reducedMotion` are context options, not page options. Reusing a context across breakpoints silently keeps the old media-query state. |
| Attach error collectors before `goto` | Errors during boot are the interesting ones and they are gone by the time the page settles. |
| Identity-tag elements before a sweep | Class names repeat. Tag with `data-qa="<i>"` first so a finding points at one element, not at a class. |

```js
async (page) => {
  const errs = [];
  page.on('pageerror', e => errs.push('PAGEERROR: ' + e.message.slice(0, 160)));
  page.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text().slice(0, 160)); });
  await page.goto(URL, {waitUntil: 'load', timeout: 60000});
  await page.waitForTimeout(2000);
  await page.mouse.move(20, 20);   // park the cursor off any hover-sensitive element
  return errs;
}
```

Parking the cursor matters: a marquee with `pauseOnMouseEnter` sits frozen under the default
mouse position and reads as broken.

---

## 1. `wheelTo` — trusted-input scroll to a target

**Proves** the page can actually be scrolled to a section, and gets there without desyncing a
smoother. **False positive rule:** if it never converges, that is a finding (probe 5), not a
broken probe — report the stall.

```js
const wheelTo = async (page, sel, targetTop = 120) => {
  for (let k = 0; k < 300; k++) {
    const t = await page.evaluate(s => {
      const el = document.querySelector(s);
      return el ? el.getBoundingClientRect().top : null;
    }, sel);
    if (t === null || Math.abs(t - targetTop) < 70) break;
    await page.mouse.wheel(0, Math.max(-600, Math.min(600, t - targetTop)));
    await page.waitForTimeout(100);
  }
  await page.waitForTimeout(1500);   // settle
};
```

The clamp keeps each tick within one viewport, so momentum scrolling stays predictable. The
final wait is the settle — do not shorten it.

---

## 2. Stuck entrance animation — settle-and-assert sweep

**Proves** an element that should have revealed is still invisible. This is the highest-value
probe; it catches every "the trigger never fired" bug.

**False-positive rules, all three required:**
- Element must be **on screen** — reveal libraries reverse when an element leaves the viewport,
  so "above the viewport at opacity 0" is correct behaviour, not a bug.
- Element must have **height > 0** — a zero-rect element is inside a hidden container, which is
  a different finding (probe 3).
- Sample must be **after settle** — an opacity between 0.1 and 0.9 is a running tween.

```js
async (page) => {
  await page.evaluate(() => document.querySelectorAll(REVEAL_SEL)
    .forEach((el, i) => el.setAttribute('data-qa', i)));

  const sections = await page.evaluate(() =>
    [...document.querySelectorAll('section')].map((s, i) => ({i, cls: s.className.trim().split(/\s+/)[0]})));

  const findings = [];
  for (const sec of sections) {
    await wheelTo(page, `section:nth-of-type(${sec.i + 1})`, 100);
    const bad = await page.evaluate((i) => {
      const out = [];
      document.querySelectorAll('section')[i].querySelectorAll(REVEAL_SEL).forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.height === 0) return;                    // hidden container -> probe 3
        if (r.bottom < 0 || r.top > innerHeight) return; // off screen -> by design
        const op = parseFloat(getComputedStyle(el).opacity);
        if (op < 0.95) out.push({qa: el.dataset.qa, cls: el.className.slice(0, 50), op,
                                 top: Math.round(r.top), h: Math.round(r.height)});
      });
      return out;
    }, sec.i);
    if (bad.length) findings.push({section: sec.cls, bad});
  }
  return findings;
}
```

`REVEAL_SEL` comes from Step 0 detection — `[data-reveal]`, `[data-aos]`, `.animate-on-scroll`,
whatever the project uses. Detection recipe is in [checks.md](checks.md#detection-recipes).

---

## 3. Hidden-container trap — animation initialised while `display: none`

**Proves** the tabs/accordion/carousel class of bug: a scroll-triggered animation was created
while its container was hidden, so the trigger measured a zero rect, never fired, and the element
stays pinned at the animation's from-state. Unhiding the container later does not help — nothing
ever plays it.

```js
async (page) => {
  return await page.evaluate(() => {
    const out = [];
    document.querySelectorAll(REVEAL_SEL).forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.height !== 0) return;
      const hiddenAncestor = el.closest('[hidden], [aria-hidden="true"]');
      let node = el, cause = null;
      while (node && node !== document.body) {
        if (getComputedStyle(node).display === 'none') { cause = node.className || node.tagName; break; }
        node = node.parentElement;
      }
      out.push({cls: el.className.slice(0, 50), op: getComputedStyle(el).opacity,
                inlineStyle: el.getAttribute('style'), hiddenAncestor: !!hiddenAncestor, displayNoneAt: cause});
    });
    return out;
  });
}
```

**Reading the result:**
- `hiddenAncestor: true` + an inline `opacity: 0` written by the animation library → **bug**. The
  panel will be blank when the user opens it. Verify by opening the panel and re-reading opacity.
- `displayNoneAt` on a whole section with no toggle in the UI → an intentionally disabled block,
  not an animation bug. Report it as dead markup (it still costs DOM nodes and triggers).

Confirmation step — open the container, then re-read:

```js
async (page) => {
  const read = () => page.evaluate(() => {
    const p = [...document.querySelectorAll(PANEL_SEL)].find(x => !x.hasAttribute('hidden'));
    return {idx: [...document.querySelectorAll(PANEL_SEL)].indexOf(p),
            inner: [...p.querySelectorAll(REVEAL_SEL)].map(e => getComputedStyle(e).opacity)};
  });
  const out = [await read()];
  for (const i of [1, 2, 0]) {
    await page.evaluate(n => document.querySelectorAll(TAB_SEL)[n].click(), i);
    await page.waitForTimeout(1200);
    out.push(await read());
  }
  return out;   // any "0" after a switch is the bug, reproduced
}
```

---

## 4. Permanent freeze — loops, marquees, autoplaying video

**Proves** an animation loop was killed by an interaction and never restarts. Common cause: an
`autoplay.stop()` / `pause()` handler with nothing that resumes it.

**False-positive rule:** wait **longer than one cycle** of the animation before the second
sample. A slider mid-transition keeps moving for seconds after its driver was killed — a 1.5 s
check reports "still moving" on a permanently dead marquee. Read the actual duration first
(Swiper `speed`, CSS `animation-duration`, video `duration`) and wait longer than that.

```js
async (page) => {
  const pos = () => page.evaluate(() => {
    const w = document.querySelector(TRACK_SEL);
    return w ? Math.round(new DOMMatrix(getComputedStyle(w).transform).m41) : null;
  });
  await page.mouse.move(20, 20);                 // hover pause must not confound the result
  const a0 = await pos(); await page.waitForTimeout(1500); const a1 = await pos();
  await page.evaluate(() => document.querySelector(TRACK_SEL).click());
  await page.waitForTimeout(7000);  const a2 = await pos();   // > one cycle
  await page.waitForTimeout(3000);  const a3 = await pos();
  return {movedBefore: a0 !== a1, movedAfterInteraction: a2 !== a3, samples: [a0, a1, a2, a3]};
}
```

`movedAfterInteraction: false` → frozen for good. On touch contexts repeat with a `tap`: a
`touchstart` handler means an ordinary scroll gesture that starts on the slider kills it.

For video, sample `currentTime` instead of transform, and also assert the viewport-gating
contract: playing while in view, paused while out.

---

## 5. Scroll hang — pin that never releases

**Proves** the page can be scrolled from top to bottom. A pinned section whose trigger fails to
release traps the user.

```js
async (page) => {
  let last = -1, stall = 0, reached = 0;
  for (let i = 0; i < 220; i++) {
    await page.mouse.wheel(0, 500);
    await page.waitForTimeout(140);
    const s = await page.evaluate(() => ({
      y: window.scrollY,
      atBottom: window.scrollY + innerHeight >= document.documentElement.scrollHeight - 5,
    }));
    reached = s.y;
    if (s.y === last) { if (++stall > 12) return {hang: true, stuckAt: s.y}; } else stall = 0;
    last = s.y;
    if (s.atBottom) break;
  }
  return {hang: false, reached, docH: await page.evaluate(() => document.documentElement.scrollHeight)};
}
```

**False-positive rule:** a pin holds `scrollY` moving while the section's `top` stays fixed —
that is a working pin, not a hang. Only a frozen `scrollY` is a hang. Sample the pinned
section's progress driver (dash offset, active-step count, timeline progress) alongside, to prove
the pin is scrubbing rather than stuck:

```js
const probe = [];
for (let i = 0; i < 14; i++) {
  await page.mouse.wheel(0, 250); await page.waitForTimeout(220);
  probe.push(await page.evaluate(() => {
    const r = document.querySelector(PINNED_SEL);
    const fill = r.querySelector(PROGRESS_SEL);
    return {top: Math.round(r.getBoundingClientRect().top),
            progress: fill ? Math.round(parseFloat(fill.style.strokeDashoffset || 0)) : null,
            active: r.querySelectorAll('.is-active').length,
            y: Math.round(window.scrollY)};
  }));
}
// healthy: top pinned near 0 for several ticks, progress marching, active count climbing, then release
```

---

## 6. Anchors — click path and direct-load path

**Proves** in-page navigation works. The two paths fail independently: clicks are usually
intercepted by JS, direct loads rely on the browser's native fragment jump — which does **not**
survive a transform-based smooth-scroll proxy, and on touch fires before below-the-fold images
have sized the page.

```js
// A. click path
async (page) => {
  const out = [];
  for (const hash of ANCHORS) {
    await page.click(`${NAV_SEL} a[href$="${hash}"]`);
    await page.waitForTimeout(2200);
    out.push(await page.evaluate((h) => {
      const t = document.querySelector(h);
      const header = document.querySelector(HEADER_SEL)?.getBoundingClientRect().height || 0;
      const r = t.getBoundingClientRect();
      return {hash: h, targetTop: Math.round(r.top), headerH: Math.round(header),
              landed: Math.abs(r.top) < 120, url: location.hash};
    }, hash));
  }
  // then: 12 rapid clicks alternating two anchors, confirm the page still scrolls afterwards
  return out;
}

// B. direct-load path — one fresh context per hash, and trace when the scroll happens
async (page) => {
  const browser = page.context().browser();
  const out = {};
  for (const hash of [...ANCHORS, '#definitely-missing']) {
    const c = await browser.newContext(VIEWPORT);
    const p = await c.newPage();
    await p.addInitScript(() => {
      window.__t = [];
      const rec = t => window.__t.push(t + '=' + Math.round(window.scrollY));
      document.addEventListener('DOMContentLoaded', () => rec('DCL'));
      window.addEventListener('load', () => rec('load'));
      [400, 1800, 3000].forEach(ms => setTimeout(() => rec('t' + ms), ms));
    });
    await p.goto(URL + hash, {waitUntil: 'load', timeout: 60000});
    await p.waitForTimeout(2500);
    out[hash] = await p.evaluate(h => {
      const t = document.querySelector(h);
      return {trace: window.__t, scrollY: Math.round(window.scrollY),
              landed: t ? Math.abs(t.getBoundingClientRect().top) < 120 : null};
    }, hash).catch(() => ({invalidSelector: true}));
    await c.close();
  }
  return out;
}
```

Also assert the header does not cover the landing point (`targetTop` vs header height — content
sitting below the header band is fine, a title under it is not), that a missing hash degrades
quietly, and that the page still scrolls after a programmatic jump.

---

## 7. Overlay and scroll-lock leak

**Proves** an opened overlay closes on every documented path, and that the body scroll lock is
released. A leaked lock leaves the page unscrollable with no visible cause.

```js
async (page) => {
  const st = () => page.evaluate(() => ({
    open: document.querySelector(OVERLAY_SEL).classList.contains(OPEN_CLASS),
    lock: document.body.classList.contains(LOCK_CLASS),
    transform: getComputedStyle(document.querySelector(OVERLAY_SEL)).transform,
  }));
  const out = {closed: await st()};
  await page.tap(TRIGGER_SEL);       await page.waitForTimeout(600); out.opened      = await st();
  await page.tap(CLOSE_SEL);         await page.waitForTimeout(600); out.viaClose    = await st();
  await page.tap(TRIGGER_SEL);       await page.waitForTimeout(600);
  await page.tap(`${OVERLAY_SEL} a`); await page.waitForTimeout(1100); out.viaLink   = await st();
  await page.tap(TRIGGER_SEL);       await page.waitForTimeout(600);
  await page.mouse.click(5, 5);      await page.waitForTimeout(600); out.viaOutside  = await st();
  for (let i = 0; i < 8; i++) { await page.tap(TRIGGER_SEL); await page.waitForTimeout(90); }
  await page.waitForTimeout(900);    out.afterRapidToggle = await st();
  const y1 = await page.evaluate(() => window.scrollY);
  await page.mouse.wheel(0, 600); await page.waitForTimeout(600);
  out.stillScrolls = y1 !== (await page.evaluate(() => window.scrollY));
  return out;
}
```

If a `tap` times out with "subtree intercepts pointer events", that is itself the finding: the
overlay never closed and is covering the control.

---

## 8. Dead selector — JS that binds to nothing

**Proves** a handler's selector matches zero elements, so a feature silently does nothing. The
classic: a CMS renders menu anchors as absolute URLs (`https://site/#pricing`) while the JS looks
for `a[href^="#"]`.

```js
async (page) => {
  return await page.evaluate(() => ({
    // one entry per selector harvested from the source
    'menu a[href^="#"]':   document.querySelectorAll('.menu a[href^="#"]').length,
    'menu a (all)':        document.querySelectorAll('.menu a').length,
    firstHrefAttr:         document.querySelector('.menu a')?.getAttribute('href'),
  }));
}
```

Workflow: grep the source for every `querySelector*` argument and every `addEventListener` target
in the site's JS, then run each selector in the live DOM. Count `0` where the feature is expected
to exist is a finding — and it points straight at the source line.

---

## 9. Latent-code harness — exercising code paths the current content does not reach

**Proves** a handler is correct even when the site's current content never triggers it (a submenu
handler on a menu with no submenus, an empty-state branch, an error branch). Inject the markup
**before** the page's own scripts bind.

```js
async (page) => {
  await page.addInitScript(() => {
    let done = false;
    new MutationObserver(() => {
      if (done) return;
      const menu = document.querySelector('.header .menu');
      if (!menu || menu.children.length < 2) return;
      done = true;
      [0, 1].forEach(n => {
        const li = menu.children[n];
        li.classList.add('menu-item-has-children');
        li.querySelector('a').setAttribute('href', '#');   // neutralise competing handlers
        const sub = document.createElement('ul');
        sub.className = 'sub-menu';
        sub.innerHTML = '<li><a href="#">child ' + n + '</a></li>';
        li.appendChild(sub);
      });
    }).observe(document, {childList: true, subtree: true});   // NOT documentElement
  });
  await page.goto(URL, {waitUntil: 'load', timeout: 60000});
  // ... then drive the feature and assert its state machine
}
```

Two details that cost real debugging time:

- Observe **`document`**, not `document.documentElement`. At document-start the latter is `null`,
  `observe()` throws, and the rest of the init script silently never registers.
- **Neutralise competing handlers on the injected nodes.** A parent link whose `href` carries a
  hash also fires the site's smooth-scroll handler; `preventDefault()` in one listener does not
  stop the others, so the page scrolls, a scroll handler closes the thing you just opened, and
  the probe reports a bug that does not exist. Setting `href="#"` isolates the unit under test.

If the probe's own state machine looks impossible (one click = closed, two clicks = open), assume
handler interference before assuming a product bug, and prove which listener fired.

---

## 10. Responsive matrix

**Proves** each breakpoint independently. Touch is not "desktop but narrow": smooth-scroll
libraries commonly disable themselves on coarse pointers, sliders switch to `centeredSlides`,
pinned sections fall back to unpinned variants — all different code.

```js
async (page) => {
  const browser = page.context().browser();
  const MATRIX = [
    ['desktop-1440', {viewport: {width: 1440, height: 900}}],
    ['laptop-1024',  {viewport: {width: 1024, height: 800}}],
    ['tablet-768',   {viewport: {width: 768,  height: 1024}, hasTouch: true, isMobile: true}],
    ['phone-390',    {viewport: {width: 390,  height: 844},  hasTouch: true, isMobile: true, deviceScaleFactor: 2}],
  ];
  const out = {};
  for (const [label, opts] of MATRIX) {
    const c = await browser.newContext(opts);
    const p = await c.newPage();
    const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 150)));
    await p.goto(URL, {waitUntil: 'load', timeout: 60000});
    await p.waitForTimeout(2500);
    out[label] = {
      errs,
      coarsePointer: await p.evaluate(() => matchMedia('(pointer: coarse)').matches),
      overflowX: await p.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1
        ? document.documentElement.scrollWidth - innerWidth : 0),
      // ... run probes 2, 4, 5, 7 here
    };
    await c.close();
  }
  return out;
}
```

`overflowX > 0` is a horizontal-scroll bug — always report it, it is invisible in a screenshot
but obvious to a user on a phone.

---

## 11. Reduced motion

**Proves** the accessibility path still shows content. The dangerous failure is not "no
animation" — it is content that stays at the animation's from-state forever because the JS bailed
out early while the CSS still hides it.

```js
async (page) => {
  const c = await page.context().browser().newContext({viewport: {width: 1440, height: 900}, reducedMotion: 'reduce'});
  const p = await c.newPage();
  // full wheel sweep (probe 2 assertions), then:
  const invisible = /* any on-screen element with height > 0 and opacity < 0.95 */;
  await c.close();
  return invisible;   // must be empty
}
```

Also worth stating in the report: a stack whose comments claim "disabled for reduced motion"
while the guard lives only in CSS behaves differently from one guarded in JS. Verify which, and
say so — the user's own machine may report `reduce`, so their manual testing and a default
browser run will disagree.

---

## 12. Clickable inventory (run before any interaction)

**Proves** nothing by itself — it is the safety gate that decides what may be clicked at all.

```js
async (page) => {
  return await page.evaluate(() => {
    const origin = location.origin;
    return [...document.querySelectorAll('a[href], button, [role="button"]')].map(el => {
      const href = el.getAttribute('href') || '';
      let sameOrigin = false, hash = '';
      try { const u = new URL(el.href || href, location.href); sameOrigin = u.origin === origin; hash = u.hash; } catch {}
      return {
        tag: el.tagName, text: el.textContent.trim().slice(0, 30), href: href.slice(0, 60),
        target: el.getAttribute('target'), rel: el.getAttribute('rel'),
        type: el.getAttribute('type'), inForm: !!el.closest('form'),
        aria: {expanded: el.getAttribute('aria-expanded'), controls: el.getAttribute('aria-controls'),
               selected: el.getAttribute('aria-selected'), role: el.getAttribute('role')},
        sameOrigin, hash, dataAttrs: Object.keys(el.dataset),
      };
    });
  });
}
```

Classify the result with the policy table in [checks.md](checks.md#clickable-element-policy)
before touching anything. Report the classification in the audit output so the user can see
exactly what was and was not exercised.
