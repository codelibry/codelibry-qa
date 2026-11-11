> Deep-QA mode of the `codelibry-qa` skill, imported from the chef `qa-browse` skill.
> `/codelibry-qa qa <url>` runs the audit below; `/codelibry-qa qa fix` runs the fix workflow and
> needs the site's source checked out. Wherever this file says `/qa-browse`, read `/codelibry-qa qa`.
> In claude.ai chat or Cowork there is no Playwright MCP to install: skip the install offer in Step -1,
> drive the browser tool you have (e.g. Claude in Chrome), and run the probe snippets through its
> JavaScript tool. Probes that need trusted wheel input or separate browser contexts run as far as
> that tool allows; say which ones you could not run.

# QA Browse — live-browser QA (audit + fix)

## Overview

Drives a real browser over a running site and measures behaviour instead of guessing at it.
Catches the bug class that reading code never finds: an entrance animation whose trigger never
fired, a marquee that stops forever on first click, an overlay that stays up with the body
locked, a `#hash` URL that lands nowhere, a pin that never releases.

Stack-agnostic: it **detects** the animation/scroll stack, then adapts the probes. The probe
choice depends on the stack — a smooth-scroll proxy forbids programmatic scrolling, a Swiper
marquee needs transform sampling, a CSS-only site needs neither.

- Probe snippets: [probes.md](probes.md)
- Check catalog, detection recipes, click policy: [checks.md](checks.md)

## Modes

Read the invocation argument:

| Invocation | Mode | Behaviour |
|---|---|---|
| `/qa-browse` | audit | Report-only. No edits, no build. |
| `/qa-browse audit` | audit | Same. |
| `/qa-browse fix` | fix | Audit, then root-cause, patch, rebuild, re-verify. |

Anything unrecognised → audit. State the mode in the first line of output.

## Step -1 — Preflight (before anything else)

This skill is useless without a working browser. Establish that first, in this order, and stop
with a plain explanation if any step fails. Never substitute code reading for a browser run and
never report a result you did not measure.

1. **Load the Playwright tools.** They are deferred — their schemas are not in context, so calling
   them directly fails. Fetch them with ToolSearch before the first use:

   ```
   ToolSearch: select:mcp__plugin_playwright_playwright__browser_run_code_unsafe,mcp__plugin_playwright_playwright__browser_navigate,mcp__plugin_playwright_playwright__browser_take_screenshot
   ```

   Add `browser_click`, `browser_hover`, `browser_console_messages`, `browser_snapshot` when the
   run needs single interactions visible in the transcript.

2. **No match returned ⇒ the MCP server is absent or disconnected. Offer to install it.**

   Ask first with `AskUserQuestion` — installing writes to the user's config, so it is their call,
   not an assumption:

   - *Install for this project* (recommended) — `--scope project`, lands in `.mcp.json`, gets
     committed, so everyone on the repo has it.
   - *Install for me globally* — `--scope user`, available in every project on this machine.
   - *Don't install* — stop the run and say what could not be checked.

   On approval:

   ```bash
   claude mcp add playwright --scope project -- npx -y @playwright/mcp@latest
   npx -y playwright install chromium     # only if the browser binary is missing
   ```

   Then verify, in this order:

   - `claude mcp list` shows the server.
   - ToolSearch again — **with a keyword query, not a `select:`**, because a CLI-installed server
     uses a different tool prefix (`mcp__playwright__browser_*`) than a plugin-provided one
     (`mcp__plugin_playwright_playwright__browser_*`). Search `+browser navigate` and read the real
     names out of the result. Use whatever prefix comes back for the rest of the run — never
     hardcode one.
   - If the tools still do not resolve, the server is registered but not connected in this session:
     tell the user to restart the session (or run `/mcp`), then re-run the skill. Say it plainly and
     stop — do not retry in a loop.

   Mention that the prefix in the project's `.claude/settings.json` is written for the
   plugin-provided server. If the CLI-installed one is used instead, the allow-list entries need
   the matching prefix or every call will prompt for permission. Offer to update it.

   If the user declines the install: stop. Do not fall back to guessing from source, and do not
   report findings that were never measured.

3. **Confirm the browser actually drives.** One `browser_navigate` to the target URL. Treat these
   as hard stops, each with its own message:
   - connection refused / DNS failure ⇒ the site is not running (a local dev host usually means
     the local server is stopped). Ask the user to start it.
   - HTTP 4xx/5xx or a WordPress fatal ⇒ report that and stop; QA of an error page is worthless.
   - redirect to a different origin (staging auth wall, maintenance mode) ⇒ report where it landed
     and confirm with the user before continuing.

4. **Mid-run disconnects happen.** If a Playwright call starts failing with an unavailable-tool
   error, re-run ToolSearch once to pick the reconnected server back up. Still gone ⇒ stop and
   report partial results, stating explicitly which pages, breakpoints and probes were covered and
   which were not. Partial coverage reported as complete is the worst possible output of this
   skill.

## Step 0 — Detect, then confirm (both modes, always)

Read-only sweep first (Glob/Grep/Read, plus one `browser_navigate` + `browser_evaluate` if a URL
is already known), then ONE `AskUserQuestion` call to confirm. **Max 4 options per question.**
Pre-fill every detected value as the first option and put the raw detected values in the question
body so the user can correct via "Other".

1. **Target URL** — local dev host / staging / production / other. Detect from `.env`,
   `.env.example`, deploy scripts in `package.json`, `*.local` naming.
2. **Page scope** — the detected page list / cap at N pages / single page / this one URL. Build
   the list from internal links on the entry page, `sitemap.xml`, or `wp-json/wp/v2/pages` on
   WordPress.
3. **Breakpoints** — default `1440 / 1024 / 768 / 390`; add `1920` when the CSS has a container
   max-width above 1440. Derive candidates from the SCSS breakpoint mixins.
4. **Animation stack + build command** — detected stack (GSAP ScrollTrigger / ScrollSmoother /
   Swiper / Lenis / AOS / CSS-only), whether a smooth-scroll proxy is active, and the build script.

Detection recipes: [checks.md](checks.md#detection-recipes). Never assume —
derive, then confirm. Skipping Step 0 is a violation.

## Audit workflow (read-only)

Track the steps with TodoWrite. Run per page × per breakpoint.

1. **Baseline** — fresh `BrowserContext` per breakpoint; `hasTouch: true, isMobile: true` for
   phone widths, because touch changes code paths (smooth-scroll libraries commonly disable
   themselves on coarse pointers, so the desktop result proves nothing about mobile). Attach
   `pageerror` and `console` collectors **before** `goto`.
2. **Clickable inventory** — classify every `a` and `button` before touching anything: href,
   `target`, `rel`, form membership, `aria-*`, `data-*`. Split into safe / verify-only / never
   per the policy table. This step is mandatory; it is what keeps the run from firing an external
   CTA or submitting a form.
3. **Full sweep** — wheel down the whole page with trusted input, section by section: reach the
   section, settle, then assert. Collect stuck entrance animations, scroll hangs, layout
   overflow, console errors.
4. **Interactive probes** — tabs, accordions, toggles, sliders, burger menu, dialogs. Safe list
   only. Each one: state before → interact → state after → state after settle.
5. **Freeze probes** — sample motion, interact, then wait **longer than the animation's own
   cycle** before sampling again. A loop mid-transition still looks alive for seconds after its
   driver was killed.
6. **Anchor probes** — every in-page anchor: click-navigation and direct `goto(url + '#id')`.
   Both paths break independently.
7. **Reduced-motion pass** — one context with `reducedMotion: 'reduce'`. Nothing may stay
   invisible; entrance animations that are JS-gated on reduced motion must still leave content
   readable.
8. **Root-cause in source** — for each symptom, grep the source for the selector, attribute or
   handler involved and cite a real `path:line` you read. A symptom whose cause you could not
   locate is reported as "cause not located", never as a guess.
9. **Report** — one line per finding:

```
path:line: <emoji> <severity>: problem. fix.
```

Severity `🔴 critical / 🟠 major / 🟡 minor / 🔵 nit`. Every finding carries the measured
evidence that produced it (the numbers — `opacity: 0 after 2.5s settle`, `scrollY 0 at t3000`),
and the breakpoint and mode it was found in. No praise, no edits, no scope creep. End with what
still needs a human eye (visual taste, copy, brand).

## Fix workflow

Audit first. If an audit already ran earlier in this session, reuse those findings rather than
re-running the whole sweep — but re-measure any finding you are about to patch.

Per confirmed finding:

1. **Root cause, not symptom.** Grep every caller of the function or selector before editing. One
   guard in the shared path beats a guard per caller, and patching only the reported path leaves
   the sibling callers broken.
2. **Minimum diff.** Prefer deleting code over adding it, CSS over JS, native platform behaviour
   over a new handler. A stuck scroll-reveal inside a tab panel is fixed by removing the reveal
   attribute and letting a CSS `.is-active` animation run — not by teaching the reveal library
   about tabs.
3. **Build.** Run the detected build command. Built output is typically gitignored and served
   directly, so a source edit changes nothing on the page until the build runs.
4. **Re-run the exact probe that caught it.** Report before/after numbers. Never claim a fix from
   a code reading — the claim must come from a measurement.
5. **Clean up** artifacts (screenshots, `.playwright-mcp/`), then report what changed, what was
   verified, and what was deliberately left alone.

Hard stops: no `git commit`, no deploy, no push, no fixes outside the confirmed findings. If a
finding needs a design decision (which of two behaviours is intended), report it and ask — do not
pick for the client.

## Rules

- **Never click**: `target="_blank"`, any link to another host, `mailto:` / `tel:`, form submits,
  admin URLs, `?action=`, logout, cart / checkout / purchase controls, download links. Verify
  those by href / target / rel / aria and by hover-state animation only. Many production sites
  point every CTA at a different domain — clicking one ends the run and can trigger a real
  side effect.
- **Never programmatically scroll** (`window.scrollTo`, `scrollIntoView`, `element.focus()`) when
  a smooth-scroll proxy is active. It desyncs the library's virtual position from
  `window.scrollY` and every subsequent reading is garbage. Use wheel input.
- **Never report a mid-animation sample as a bug.** Settle first; an opacity of 0.37 is a tween
  in progress, not a defect.
- **Never treat "off-screen and invisible" as broken.** Reveal libraries commonly reverse when an
  element leaves the viewport. Only elements that are on screen, have height, and stay invisible
  after settling are bugs.
- **Prefer `browser_run_code_unsafe`** for multi-step probes: one call instead of thirty, and it
  is the only way to get trusted `page.mouse.wheel` input and per-breakpoint `BrowserContext`s.
  Use the individual `browser_*` tools for single interactions and for anything the user should
  see in the transcript.
- **Screenshots go to the scratchpad directory**, never the repo root. Delete any that land in
  the working tree before reporting.
- **Check which build is live.** Production may serve an older bundle than the local source;
  confirm before blaming source code, and say so if the two disagree.
- **Report the context of every finding** — breakpoint, touch or mouse, normal or reduced motion.
  The same page behaves differently in each.
