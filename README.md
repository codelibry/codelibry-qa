# codelibry-qa

> **Claude:** if a user gave you this link and asked you to set it up, read
> [`codelibry-qa/SKILL.md`](codelibry-qa/SKILL.md) and follow its **Setup** section.

A Claude skill for agencies that maintain websites. Every morning Claude checks your sites and
replies in the chat with one report, with what to do about each problem. Nothing is installed on
the sites, and it needs no server and no connectors.

## How to use

1. Open a scheduled task chat in Claude (claude.ai or Cowork).
2. Paste this repository's link and your site, for example:
   `Set this up: https://github.com/codelibry/codelibry-qa — site: https://example.com`
3. Claude scans the site, lists every form it found, and asks you once for the test data to submit
   (name, email, phone, message). It then posts a **config block** in the chat and runs the first
   check.
4. Give the scheduled task the prompt Claude suggests, e.g. "Run codelibry-qa with the latest
   config in this chat".
5. Later, add sites in the same chat: "add https://another-site.com".

Test submissions reach the site owner every run, marked `[TEST] … please ignore`. Tell your
clients.

## All checks

**Site and server**
1. Home page HTTP status (5xx, 4xx, no response).
2. DNS failure, timeout or refused connection.
3. Redirect to a different domain (hack, expired hosting).
4. Response time over 10 s.
5. SSL certificate: days left (warning < 14, critical < 3) and handshake errors. Behind a network
   proxy that swaps certificates, the date comes from the public Certificate Transparency log
   (Cert Spotter).
6. WordPress error screens: "critical error on this website", "Error establishing a database
   connection", stuck "Briefly unavailable for scheduled maintenance".
7. PHP Fatal / Parse errors printed on the page.
8. PHP Warnings / Notices / Deprecated printed on public pages (`WP_DEBUG_DISPLAY` left on).

**SEO blockers**
9. `noindex` on the home page (meta robots or `X-Robots-Tag`), often left over from staging.
10. `robots.txt` blocking the whole site (`Disallow: /` for all crawlers).

**Whole-site crawl** (sitemap + internal links, 100 pages by default)
11. Every crawled page: 404 / 410 / 5xx, with the pages linking to it.
12. WordPress or PHP errors on any crawled page.
13. Broken internal links.
14. Broken external links (404 / 410 / dead domain).
15. Broken images, CSS, JS, iframes, preloaded fonts and favicons.
16. Mixed content: http:// files on https pages.
17. Leftover editor notes and filler on any crawled page: "(confirm: …)", TODO, lorem ipsum,
    `{{placeholder}}`.
18. Links from hosts that block bots (LinkedIn, some CDNs): listed as unverified, not broken.

**In the browser**
19. The page actually renders: no blank page or error screen.
20. JS console errors from the site's own scripts. Third-party noise is ignored.
    A CDN "Checking your browser" page is waited out; if it doesn't clear, that's reported as not
    checked.

**Forms**
21. Inventory of every form on the site: contact, newsletter, quote, booking. That includes
    script-drawn forms found by their embed code and ID: HubSpot, Ninja Forms, Typeform, Jotform,
    Google Forms, Tally, Cognito, Zoho, ActiveCampaign, Pipedrive, Microsoft Forms, Klaviyo,
    Calendly. Search, login, comment, cart and booking forms are recognised and never submitted.
22. Script-drawn form whose embed is on the page but which never renders in the browser.
23. Missing form: in the config, gone from the site.
24. New form: on the site, not yet in the config. Reported, not submitted until you add it.
25. Test submission of every configured form, with the result the site shows: sent, mail error
    (e.g. CF7 "There was an error trying to send your message"), validation error, spam/captcha
    rejection, or no response. For Contact Form 7 the server's own status (`mail_failed`, `spam`,
    …) tells a mail failure from an antispam rejection. Forms in a closed popup and multi-step
    forms are found but not submitted.
26. Captcha challenge: reported as "needs a human". Never solved.

**Report** ([format](codelibry-qa/references/report.md)): a summary line, then per site a table of all
26 checks above (✅ / ⚠️ / ❌ / ➖ not checked) and numbered problems, each with where, evidence and
action. Then every test submission made, and what wasn't checked. With more than 5 sites, Claude
asks once whether the full report may go into an artifact: the chat then gets only the problems
and a link.

Also included: `qa <url>`, a deep live-browser QA pass (animations, breakpoints, interactive
components, reduced motion).

## What the chat needs

| Tool | Enables |
|---|---|
| Code execution with internet access to your sites | Checks 1–18, 21, 23 and 24 (`site_check.py`, Python standard library only). |
| A headless browser in the sandbox (Claude Code cloud sessions ship Chrome) | Checks 19–20, 22 and 25–26 (`browser_check.mjs`). Your computer doesn't need to be on. |
| Otherwise: Claude in Chrome / Cowork browser | The same browser checks, while your computer is on. |
| Web fetch only | Status, errors and form presence on the main pages. |

**Network:** a cloud environment blocks unknown sites by default. Set its **Network access** to
**Full**, or add your sites' domains and `api.certspotter.com` to **Allowed domains**. Claude
checks this during setup and gives you the exact steps.

Claude tells you during setup what it has and what that leaves out. Each run reads the skill from
the repository attached to the task, or from a pinned commit, never from a moving branch. Say
"update the skill" to move to a newer commit.

## Not checked

- Whether the notification email arrives. Only the site's response to the submission is checked.
- Domain expiry, uptime between runs, performance scores.

## Develop

```bash
python3 -m unittest discover tests
npm install --prefix codelibry-qa/scripts && CHROME_PATH=/usr/bin/chromium node --test tests/browser_check.test.mjs
python3 codelibry-qa/scripts/site_check.py https://example.com
```
