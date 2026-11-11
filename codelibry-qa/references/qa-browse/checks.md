# qa-browse — Detection Recipes, Check Catalog, Click Policy

Reference for the `qa-browse` skill. Stack-agnostic: every check is phrased to adapt to whatever
Step 0 detected. Severity: 🔴 critical / 🟠 major / 🟡 minor / 🔵 nit.

Probe snippets live in [probes.md](probes.md).

---

## Detection Recipes

Run these read-only before the Step 0 confirmation questions, and pre-fill the answers from what
you find. Never hardcode a project's conventions — derive them.

| What | How to detect |
|---|---|
| Target URL | `.env` / `.env.example` (`*_FTP_*`, `*_URL`), deploy scripts in `package.json`, a `*.local` host in the project path, `wp-config.php` `WP_HOME`. Ask which environment to run against — never assume production. |
| Page list | Internal `a[href]` on the entry page filtered to same origin; `sitemap.xml`; `wp-json/wp/v2/pages?per_page=100` on WordPress. Deduplicate by pathname, drop hashes. |
| Breakpoints | SCSS/CSS `@media` widths and any breakpoint mixins (`@include md`, `$breakpoints` map). Take the distinct widths, add one above the largest container max-width. |
| Animation stack | `package.json` deps and JS imports: `gsap` (+ `ScrollTrigger`, `ScrollSmoother`, `DrawSVGPlugin`), `swiper`, `lenis`/`@studio-freight/lenis`, `aos`, `framer-motion`, `locomotive-scroll`. No deps + `@keyframes`/`transition` in CSS ⇒ CSS-only. |
| Smooth-scroll proxy | DOM for `#smooth-wrapper`/`#smooth-content`, `[data-lenis]`, `.has-scroll-smooth`; or a transform on the content wrapper while `window.scrollY` stays 0. **If present, programmatic scrolling is banned for the whole run.** |
| Entrance-animation selector | The attribute/class the project drives reveals with: `[data-reveal]`, `[data-aos]`, `[data-animate]`, `.reveal`, `.fade-up`. Grep the JS for the selector it queries, not the CSS. |
| Initial-state CSS | The rule that hides reveal targets before JS runs (`opacity: 0` on the reveal selector). Its existence means **JS failure = permanently invisible content**, which raises every stuck-animation finding to 🔴. |
| Interactive components | Roles and conventions in markup: `role="tab"`/`aria-controls`, `aria-expanded` (accordion), `[hidden]` panels, `.swiper`, `<dialog>`, burger button, `aria-pressed` toggles. |
| Scroll-lock convention | The class or style applied to `body`/`html` when an overlay opens (`.lock`, `.no-scroll`, inline `overflow: hidden`). |
| Build command | `package.json` scripts — `build` (production), `start`/`dev` (watch). Note the output dir and whether it is gitignored. |
| Live-bundle drift | Compare the hash/size/mtime of the served bundle against the local build output. A production URL may run an older bundle than the source you are reading. |

---

## Clickable Element Policy

Build the inventory (probe 12) **before** any interaction, classify every row, and report the
classification. When a row is ambiguous, it goes in the "never" column.

### Safe to click

- In-page anchors: same origin, same pathname, non-empty hash, and the target exists.
- `role="tab"` / `[aria-controls]` tab buttons.
- Accordion headers (`aria-expanded` present).
- Toggles and switches (`aria-pressed`, filter/segment controls) whose effect is client-side.
- Carousel arrows, dots, and pagination bullets.
- Menu open/close controls: burger, close button, overlay backdrop.
- `<dialog>` open/close triggers where the dialog stays on the page.

### Verify without clicking

Assert their attributes, their hover/focus animation, and their computed styles — never activate
them:

- Any link with `target="_blank"`.
- Any link to a different host (external CTAs, app subdomains, docs).
- `mailto:` and `tel:`.
- Links whose href is a file download.
- Pagination or filter links that navigate to a different pathname — if their destination matters,
  reach it with `goto`, not with a click.

For these, check: href resolves and is not empty/`#`; `target="_blank"` carries `rel="noopener"`;
accessible name is not empty; the hover transition actually runs (compare computed style before
and after `page.mouse.move` onto the element).

### Never touch

- `type="submit"`, any control inside a `<form>`, and Enter-key submission.
- Admin URLs, `?action=`, `logout`, `/wp-admin`, `/wp-login.php`.
- Cart, checkout, subscribe, purchase, "delete", "remove", "cancel".
- Anything whose `data-*` or text implies a real side effect (booking, payment, sending).
- File inputs and upload controls.

**When in doubt, do not click.** A missed interactive check is a line in the report; a fired CTA
is a real-world side effect and the end of the run.

---

## Check Catalog

### A. Entrance animations (scroll reveals)

- **A1** Every reveal target that is on screen, has height, and has settled reads `opacity ≥ 0.95`. Stuck at the from-state ⇒ invisible content. 🔴 (🟠 if the CSS does not pre-hide, so the content is readable and only the motion is lost.)
- **A2** No reveal target initialised inside a `[hidden]` / `display: none` container. Zero rect at trigger-creation time ⇒ the tween never plays and the panel is blank when opened. 🔴
- **A3** Reveal targets revealed once per entry and not re-hidden while still on screen (a reverse action firing mid-viewport reads as content vanishing under the user). 🟠
- **A4** Staggered containers reveal every child, not just the first. 🟠
- **A5** Reveal triggers survive a resize / late font or image load (positions recalculated — a `refresh` on `load` or `invalidateOnRefresh`). Content below a late-sizing image otherwise never triggers. 🟠
- **A6** No reveal attribute left on an element the project never animates (dead attribute holding `opacity: 0` if the library changes). 🔵

### B. Scroll-driven and pinned sections

- **B1** The page scrolls from top to bottom without stalling. A frozen `scrollY` over a dozen wheel ticks ⇒ trapped user. 🔴
- **B2** A pin releases: section top fixed for its scrub range, then it scrolls away normally. 🔴
- **B3** The scrub driver actually advances with scroll (progress value, active-step count, dash offset), and is reversible on the way back up. 🟠
- **B4** Pinned/scrubbed sections have a non-pinned fallback below their breakpoint, and it works. 🟠
- **B5** No layout jump when the pin engages or releases (spacer height correct). 🟡

### C. Loops, marquees, autoplay media

- **C1** The loop still runs after the interactions a user makes: click, tap, drag, hover-out. Sampled after **more than one cycle**. A permanent stop ⇒ dead section. 🔴
- **C2** Hover-pause resumes on mouse-out. 🟠
- **C3** Autoplaying video honours its viewport gate: playing in view, paused out of view; `muted` + `playsinline` present or autoplay is silently rejected. 🟠
- **C4** A video-driven sequence has a fallback when `play()` rejects (no autoplay permission) — otherwise the sequence stalls on the first slide forever. 🟠
- **C5** Looping media does not keep decoding off-screen (battery/CPU). 🔵

### D. Interactive components

- **D1** Tabs: every panel switches, the newly shown panel's content is visible, `aria-selected` / `hidden` / roving `tabindex` follow. 🔴
- **D2** Accordion: opens, closes, single-open contract holds if that is the design, `aria-expanded` matches. 🟠
- **D3** Toggles (pricing monthly/yearly, filters): the visible values actually change, not just a class. Assert rendered text, not only the class name. 🔴
- **D4** Slider: navigation controls move it, loop wraps, drag works on touch, no blank slide at the wrap point. 🟠
- **D5** Keyboard: arrow/Home/End on a tablist, Escape closes an overlay, focus is visible and does not get trapped. 🟠
- **D6** Rapid repeated interaction leaves a consistent state (8 fast toggles ⇒ the state machine still agrees with the DOM). 🟠

### E. Overlays and scroll lock

- **E1** Every documented close path works: close button, in-overlay link, outside click, Escape. 🔴
- **E2** The scroll lock is released on every close path; the page scrolls afterwards. A leaked lock is invisible and total. 🔴
- **E3** The overlay's own transition runs (transform/opacity change between states), not an instant snap where an animation was intended. 🟡
- **E4** An open overlay does not leave the trigger unreachable underneath (pointer-events check). 🟠

### F. Navigation and anchors

- **F1** Every in-page anchor scrolls to its target on click. 🔴
- **F2** Every in-page anchor works on **direct load** (`site/#id`). Native fragment jumps do not survive transform-based smooth scrolling and fire too early on touch. 🔴
- **F3** A missing/invalid hash degrades quietly — no exception, page usable. 🟠
- **F4** The landing point is not hidden behind a fixed header. 🟡
- **F5** Rapid repeated anchor clicks do not lock scrolling. 🟠
- **F6** `history` state matches what the user sees (hash updated, back button sane). 🔵
- **F7** External links carry `rel="noopener"` with `target="_blank"`. 🟡

### G. Responsive

- **G1** No horizontal overflow at any breakpoint (`scrollWidth > innerWidth`). 🟠
- **G2** Touch contexts are exercised with `hasTouch: true` — code paths differ from a narrow desktop window. 🔴 if untested behaviour breaks.
- **G3** Components that swap implementation at a breakpoint (pinned ⇄ static, carousel ⇄ stack) work on both sides of it. 🟠
- **G4** Nothing overlaps or clips at the smallest supported width; tap targets stay reachable. 🟠
- **G5** Header/menu behaviour is correct per breakpoint (burger appears, desktop nav hides, scrolled state toggles). 🟠

### H. Reduced motion

- **H1** Under `prefers-reduced-motion: reduce`, no content stays invisible. 🔴
- **H2** Motion is genuinely reduced where the code claims it is — verify whether the guard is in JS or only in CSS, and report which. 🟡
- **H3** Behaviour that is content (a product demo animation) is allowed to keep running; say so explicitly rather than flagging it. 🔵

### I. Console, network, boot

- **I1** Zero uncaught errors on load and during the sweep, at every breakpoint. 🔴
- **I2** No 404s for assets referenced by the animations (videos, SVGs, posters). 🟠
- **I3** No layout-shift storm after load (late-sizing media above the fold). 🟡
- **I4** The served bundle matches the local source — if not, say so before attributing any finding to source code. 🟠

---

## Known False Positives

Do not report these. Each one has produced a confident wrong finding before.

| Observation | Why it is not a bug |
|---|---|
| On-screen element at opacity 0.1–0.9 | A tween in progress. Settle 1.5–2 s and re-read. |
| Element above the viewport at opacity 0 | Reveal libraries commonly reverse on leave (`toggleActions: play reverse play reverse`). It is off screen; the user never sees it. |
| Zero-rect element with `opacity: 0` | Inside a hidden container. Either the hidden-container bug (verify by opening the container) or an intentionally disabled block — check whether any UI can ever show it. |
| A whole section at `display: none` with no toggle | A deliberately disabled block. Report as dead markup, not as a broken animation. |
| `window.scrollY` reading 0 while the page is visually scrolled | A smooth-scroll proxy is active and something scrolled programmatically. The reading is invalid — reset and use wheel input. |
| Slider still moving 1.5 s after its driver was killed | The in-flight transition. Wait longer than one cycle. |
| Marquee frozen under the default cursor position | `pauseOnMouseEnter`. Park the mouse away from it first. |
| A pinned section whose top stays at 0 | That is a pin working. Only a frozen `scrollY` is a hang. |
| An injected test node behaving strangely | Handler interference from the real page (see probes.md §9). Isolate before reporting. |

---

## Report Format

```
path:line: <emoji> <severity>: problem. fix.
```

Every finding carries:

- the **measured evidence** (`opacity: 0 after 2.5 s settle`, `scrollY 0 at t3000`, `transform
  unchanged after 10 s`) — numbers, not adjectives;
- the **context** (breakpoint, touch or mouse, normal or reduced motion);
- a real `path:line` in the source that you read. If the cause could not be located, say
  "cause not located" and give the reproduction steps instead of guessing.

Group by catalog section. Close with: what was verified clean (short table), what was
deliberately not exercised (the never-click list), and what still needs a human eye.
