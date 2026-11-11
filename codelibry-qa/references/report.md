# Report format

Every run's reply is this report and nothing else: no intro, no outro, no free prose between
sections. Sections always come in this order, and a section with nothing in it is left out
(except the header and the site tables). Translate every label into the config's `language`. Keep
the structure, the numbering, the emoji and the order.

## Rules

- **Status marks:** ❌ act today, ⚠️ look this week, ✅ fine, ➖ not checked this run. Nothing else.
  Severity comes from `playbook.md`.
- **Sites:** ❌ sites first, then ⚠️, then ✅, each group alphabetical. A site takes its worst
  mark. **Every site gets the full 26-row table**, a ✅ site too.
- **Problems are numbered** 1, 2, 3 within a site, ❌ before ⚠️. Each one names its check number
  and has the same three lines: **Where**, **Evidence**, **Action**. Evidence is measured: a status
  code, a quoted message, a count, a URL. Action is the playbook's reaction, shortened.
- **URLs:** paths relative to the site (`/pricing/`) for the site's own pages and files, full URLs
  for other hosts, in backticks.
- **Lists are capped:** at most 5 URLs per item, then "… and N more".
- **Numbers:** status codes as is, times in seconds with one decimal, dates as `12 Nov 2026` in
  the report's language.
- Typos and contradictions you noticed are optional. They go only in **Verify by eye**, never in
  Problems.

## The 26 checks

The numbers and order match the README's "All checks". Every row is always present.

| # | Check | Built from | Result example |
|---|---|---|---|
| | **Site and server** | | |
| 1 | Home page status | `status` | `200` |
| 2 | DNS and connection | `error` | `resolves, connects` |
| 3 | Redirect to another domain | `off_origin`, `final_url` | `none` |
| 4 | Response time | `ms` | `0.7 s` |
| 5 | SSL certificate | `tls_days_left`, `tls_source` | `82 days (CT log)` |
| 6 | WordPress error screens | `fatal` (critical error, database, maintenance) | `none` |
| 7 | PHP fatal / parse errors | `fatal`, `page_errors[].fatal` with "Fatal error" / "Parse error" | `none` |
| 8 | PHP warnings and notices | `php_notices` | `none` |
| | **Search** | | |
| 9 | Home page noindex | `noindex_home` | `indexable` |
| 10 | robots.txt | `robots_blocks_all` | `open` |
| | **Whole-site crawl** | | |
| 11 | Crawled pages | `pages_crawled`, `page_errors` status | `100 · 0 errors` |
| 12 | WordPress / PHP errors on pages | `page_errors[].fatal` | `none` |
| 13 | Internal links | `page_errors`, internal `broken_links` that are pages | `0 broken` |
| 14 | External links | external `broken_links` | `3 broken` |
| 15 | Images, CSS, JS, iframes, fonts, favicons | internal `broken_links` that are files | `2 broken` |
| 16 | Mixed content | `mixed_content` | `none` |
| 17 | Editor notes and filler | `content_leftovers` | `2 found` |
| 18 | Unverified links (hosts block bots) | `unverified_links` | `5 · not a fault` |
| | **Browser** | | |
| 19 | Pages render | browser pages: `blank`, `status`, `botChallenge` | `6/6` |
| 20 | JS console errors | browser pages: `consoleErrors`, minus playbook noise | `2 on 6 pages` |
| | **Forms** | | |
| 21 | Forms found | `forms` | `7 · 5 tested` |
| 22 | Script-drawn forms render | browser `renders` of `rendered: js` forms | `1/1` |
| 23 | Missing forms | config forms absent from `forms` | `none` |
| 24 | New forms | `forms` absent from the config | `none` |
| 25 | Test submissions | browser `submit`, `serverStatus` | `3/3 sent · 2 manual` |
| 26 | Captcha challenges | browser `submit: "captcha challenge…"` | `none` |

A row's status is the worst signal it covers. Row 18 is ✅ whatever the count. A row that couldn't
run is ➖ with the reason in a few words, and the reason goes in Not checked too.

## Template

```markdown
## 🌅 Site check · 12 Nov 2026

**2 sites** · ❌ 0 · ⚠️ 1 · ✅ 1

---

### ⚠️ codelibry.com

| # | Check | Status | Result |
|---|---|---|---|
| | **Site and server** | | |
| 1 | Home page status | ✅ | 200 |
| 2 | DNS and connection | ✅ | resolves, connects |
| 3 | Redirect to another domain | ✅ | none |
| 4 | Response time | ✅ | 0.7 s |
| 5 | SSL certificate | ✅ | 82 days (CT log) |
| 6 | WordPress error screens | ✅ | none |
| 7 | PHP fatal / parse errors | ✅ | none |
| 8 | PHP warnings and notices | ✅ | none |
| | **Search** | | |
| 9 | Home page noindex | ✅ | indexable |
| 10 | robots.txt | ✅ | open |
| | **Whole-site crawl** | | |
| 11 | Crawled pages | ✅ | 100 · 0 errors |
| 12 | WordPress / PHP errors on pages | ✅ | none |
| 13 | Internal links | ✅ | 0 broken |
| 14 | External links | ⚠️ | 3 broken |
| 15 | Images, CSS, JS, iframes, fonts, favicons | ⚠️ | 2 broken |
| 16 | Mixed content | ✅ | none |
| 17 | Editor notes and filler | ⚠️ | 2 found |
| 18 | Unverified links (hosts block bots) | ✅ | 5 · not a fault |
| | **Browser** | | |
| 19 | Pages render | ✅ | 6/6 |
| 20 | JS console errors | ⚠️ | 2 on 6 pages (the fonts in 15) |
| | **Forms** | | |
| 21 | Forms found | ✅ | 7 · 5 tested |
| 22 | Script-drawn forms render | ✅ | 1/1 |
| 23 | Missing forms | ✅ | none |
| 24 | New forms | ✅ | none |
| 25 | Test submissions | ✅ | 3/3 sent · 2 manual |
| 26 | Captcha challenges | ✅ | none |

**1. ⚠️ Theme fonts return 404** · checks 15, 20
- **Where:** every page, `<link rel="preload">` in `<head>`
- **Evidence:** 404 `/wp-content/themes/codelibry-site/assets/fonts/Poppins-Medium.woff2`,
  404 `/wp-content/themes/codelibry-site/assets/fonts/DMSans-Regular.woff2`
- **Action:** Restore the files or fix the paths in the preload links and `@font-face`.

**2. ⚠️ Editor notes visible** · check 17
- **Where:** `/`, FAQ
- **Evidence:** "(confirm: what to say when there is no Figma)", "(confirm: public)"
- **Action:** Remove them in the page editor.

**3. ⚠️ External links return 404** · check 14
- **Where:** 3 whitepaper pages; 2 case studies
- **Evidence:** 404 `https://www.youtube.com/@wp-talks`, 404 `https://www.figma.com/design/…` (×2)
- **Action:** Replace or remove them. Figma answers 404 for private files too: check access first.

---

### ✅ brochure.example.net

(the same 26-row table, all ✅ or ➖)

---

### 📨 Test submissions

| Site | Form | Page | Result |
|---|---|---|---|
| codelibry.com | CF7 #2065 | `/whitepaper/…` | ✅ sent · `mail_sent` |
| codelibry.com | CF7 #1122 | `/blog/` | ✅ sent · `mail_sent` |
| codelibry.com | HubSpot | `/how-to-build-…/` | ✅ "Form submitted" |

Each line is one `[TEST]` entry in the site owner's inbox or CRM.

### ➖ Not checked

1. Crawl stopped at 100 pages per site.
2. 5 links on hosts that block bots (LinkedIn, Clutch, Upwork).
3. codelibry.com: CF7 #2063 (multi-step) and #2064 (popup) are not submitted: test them by hand.
4. codelibry.com: Calendly is checked for rendering only.

### 👁 Verify by eye

1. `/pricing/`: "Presice estimate" looks like a typo.
```

## Many sites

With more than 5 sites, 26 rows per site is too long for a chat. The user decides once, in setup
or when the sixth site is added, and the config stores it as `artifact`. A run never asks.

- **`"artifact": true`:** put the full report above, unchanged, in an artifact titled
  `Site check · <date>`. Use the platform's artifact or page tool (claude.ai artifacts in a chat).
  Update the same artifact every run when the platform allows it, so its link stays the same. In the
  chat, post only:

  ```markdown
  ## 🌅 Site check · 12 Nov 2026

  **17 sites** · ❌ 1 · ⚠️ 2 · ✅ 14 · [Full report](<artifact link>)

  ### ❌ shop.example.org
  **1. ❌ Contact form doesn't send mail** · check 25
  - **Where:** `/contact/`, CF7 #2063
  - **Evidence:** "There was an error trying to send your message." · server `mail_failed`
  - **Action:** Check the form's Mail tab, then the SMTP plugin's log and the mail provider.

  ### ⚠️ codelibry.com
  **1. ⚠️ Theme fonts return 404** · checks 15, 20
  - …

  ### ✅ 14 sites
  a.com, b.com, c.com, …
  ```

  That's the problems in full and the ✅ sites in one line, with no 26-row tables. Test submissions,
  Not checked and Verify by eye stay in the artifact. If the artifact can't be created this run,
  post the full report in the chat instead, and say why in Not checked.
- **`"artifact": false` or no answer:** the full report in the chat, as above.

## Special cases

- **Not set up:** no config block in the chat. Reply with one line saying setup hasn't been done.
- **A whole group couldn't run** (no network, no browser): its rows are ➖ with the reason in a
  few words, and the full reason is item 1 of Not checked.
