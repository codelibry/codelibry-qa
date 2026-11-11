---
name: codelibry-qa
description: Daily health check of a list of websites, run by Claude in one chat (a claude.ai, Claude Code cloud or Cowork scheduled task), with nothing installed on the sites. Setup from a GitHub link in the chat. Finds every form on each site (including script-drawn HubSpot/Ninja/Typeform embeds), asks once for test data, then each run checks uptime, WordPress/PHP errors, SSL, noindex/robots, broken links across the site, mixed content, leftover editor notes, JS errors, and submits a test on every form. Reports in the chat with what to do for every problem. Sites are added later in the same chat. Also deep live-browser QA of one site. Use for "/codelibry-qa", "check our sites", "morning site check", "maintenance check", "broken links", "постав це", "перевір сайти", "проверь сайты", "добавь сайт".
---

# Codelibry QA

Everything happens in one chat. The user pastes this repository's link and a site. You set the
monitor up, post a config block and create the daily scheduled task. From then on the task runs
the check, and the user adds sites in the same chat. Nothing is installed on the sites, no
connectors are needed, and the report is your reply.

Every line of a report comes from something measured in that run: a status code, a quoted
message, a count. The skill is read-only on the sites, except for the test form submissions the
user agreed to in setup.

## Files

Next to this file:

- `scripts/site_check.py` — HTTP checks, SSL, link crawl, content leftovers, form inventory.
  Python standard library only.
- `scripts/browser_check.mjs` + `scripts/package.json` — headless Chrome: rendering, console,
  forms (including script-drawn ones), test submissions. Needs Node and `playwright-core`.
- `references/playbook.md` — severity and "what to do" for every signal. Read it before writing
  any report.
- `references/report.md` — the report's exact format. Every report follows it.
- `references/qa-browse/qa-browse.md` — deep QA mode.

**Where the files come from — never a moving branch.** Code downloaded from a branch at run time
can change under a running task, and safety checks rightly block it. In order of preference:

1. The repository is attached to the session or scheduled task: it is cloned at the start, so use
   the local files. This is how to create the scheduled task when the platform allows it.
2. Otherwise read the files pinned to a commit:
   `https://raw.githubusercontent.com/<owner>/<repo>/<commit-sha>/codelibry-qa/<file>`. Resolve the
   SHA once in setup, for example `git ls-remote https://github.com/<owner>/<repo> HEAD` or the
   GitHub commits page, and store it in the config as `skill`.
3. The user says "update the skill": resolve the newest SHA, list what changed in the commits
   since the pinned one, and repost the config with the new pin. Remove from the scheduled task's
   prompt any workaround the new commit makes unnecessary. The task picks it up from the next
   run.

## Which mode

| The message | Mode |
|---|---|
| A link to this repo plus "install / set up / постав / поставь", usually with site URLs | **Setup** |
| "add / додай / добавь <site>", or a bare site URL after setup | **Add site** |
| "remove <site>", new test data, "don't test form X", "add it" (a new form from a report) | **Edit config**: update it, post the new config block |
| "update the skill / онови скіл / обнови скилл" | Update the pinned commit (see Files) |
| The scheduled task's prompt, or "run / check / перевір / проверь" | **Run** |
| `qa <url>` | Deep QA: follow `references/qa-browse/qa-browse.md` |

## The config block

The chat holds the monitor's state in one fenced block. Post it at the end of Setup and after
every change, and always repost it in full. A run uses the **latest** block in the chat. If the
task runs somewhere that can't see the chat history, keep a copy of the same JSON in the
scheduled task's prompt and update both.

````
📋 codelibry-qa config
```json
{
  "skill": "https://raw.githubusercontent.com/<owner>/<repo>/<commit-sha>/codelibry-qa",
  "language": "uk",
  "max_pages": 100,
  "artifact": false,
  "test_data": {
    "name": "Codelibry QA Test", "email": "maintenance@agency.com", "phone": "+380000000000",
    "company": "Test", "message": "[TEST] Automated maintenance check, please ignore."
  },
  "sites": [
    { "url": "https://example.com/", "forms": [
      { "id": "wpcf7-2063", "plugin": "cf7", "kind": "contact", "page": "https://example.com/contact/", "rendered": "html", "test": true },
      { "id": "0f1e2d3c-…", "plugin": "hubspot", "kind": "contact", "page": "https://example.com/demo/", "rendered": "js", "test": true }
    ] }
  ]
}
```
````

## Capabilities: probe them, then say what's missing

Run these probes at the start of Setup and of every Run. In Setup, tell the user exactly how to
fix anything missing, and wait for them to do it. In a Run, put it in the report's Not checked section.

1. **Internet from code execution:** `curl -sS -o /dev/null -w '%{http_code}\n' -D - <site-url>`.
   - A normal status (200, 301, 403 from the site's CDN): available.
   - `403` with `x-deny-reason: host_not_allowed`, a proxy error, or no connection: the sandbox's
     network blocks the site.

   Tell the user, step by step, in their language:
   - **Claude Code cloud / claude.ai scheduled tasks**: open the task's cloud environment
     (claude.ai/code → environment selector → settings icon). Set **Network access** to **Full**.
     Or set it to **Limited**, keep **Allow package managers** on, and add to **Allowed domains**
     every site's domain (with and without `www.`) plus `api.certspotter.com`. The change applies
     from the next run.
   - **claude.ai chat**: Settings → Capabilities → code execution network access → allow all
     domains, or add the same domains.
2. **Headless browser:** `echo $CHROME_PATH; node --version`. Both present (Claude Code cloud
   sessions ship Chrome at `$CHROME_PATH`)? Then run
   `npm install --prefix <scripts dir> --no-audit --no-fund` and use `browser_check.mjs`. This
   needs no computer of the user's to be on.
3. **Claude in Chrome / Cowork browser:** use it only when there is no headless browser. It needs
   the user's computer on and Chrome allowed. Say so.
4. **Web fetch only:** status, fatals and form presence on the main pages. That's limited
   coverage: say it.

## Setup

Setup is interactive. Questions are expected here.

1. **Read** the skill files and resolve the commit to pin (see Files). Run the capability probes.
   Give the user one short message: what works, what doesn't, and the exact steps to fix it. If
   the network blocks the sites, ask them to fix that first and continue when they say it's done.
2. **Inventory** each site: `python3 site_check.py --max-pages 100 <url>`, and read its `forms`.
   - `"rendered": "html"` forms are real `<form>` tags.
   - `"rendered": "js"` forms are drawn by a script and found by their embed marker and ID:
     HubSpot, Ninja Forms, Typeform, Jotform, Google Forms, Tally, Cognito, Zoho, ActiveCampaign,
     Pipedrive, Microsoft Forms, Klaviyo, Calendly.
   - With a browser, run `browser_check.mjs` on a draft config with every form at `"test": false`.
     It confirms each form actually renders, without submitting anything.
   - A form the browser shows that the script missed (an unknown vendor, a popup behind a button):
     add it with `"rendered": "browser"`, its page and a `selector`.
3. **Show** per site a short health line (status, SSL days, broken-link count) and the forms
   found: kind, plugin, id, page, and the fields in plain words.
   - Forms of kind `contact`, `newsletter` and `other` will be test-submitted every run.
   - `search`, `login`, `comment`, `shop` and `booking` forms are never submitted. A Calendly
     booking would book a real meeting. List them as "not tested".
4. **Ask for test data, always, once**, in one message — even if there's no browser yet, so
   submissions start the day one is available:
   - name, email, phone, company, message;
   - which listed forms to exclude.

   Propose defaults the user can just accept. The message must start with `[TEST]`. Say plainly
   that every run, the test submissions reach the site owner's inbox and CRM. Other fields
   (budget, date, dropdowns) are filled automatically and don't need asking.

   With more than 5 sites, ask in the same message whether the full report may go into an
   artifact: the chat then gets a short summary, and the artifact holds every site's 26-check
   table. Store the answer as `"artifact": true` or `false`. Never create one without a yes.
5. **Post the config block.**
6. **Create the daily scheduled task**, if the platform lets you. Attach this repository to it
   when possible, give it a short prompt such as «Запусти codelibry-qa за останнім конфігом у
   цьому чаті», and pick a morning time a few minutes past the hour. If you can't create it, give
   the user that prompt and the steps.
7. **Run the first check right away** (Run mode), so they see a real report.

## Add site

Do Setup steps 2–3 for the new site only (and step 4 only if the existing `test_data` can't fill
one of its required fields). If this makes more than 5 sites and the config has no `artifact`
answer yet, ask the artifact question from step 4. Post the full updated config block, then run the check on the new
site only.

## Run

Unattended: never ask a question and never wait for confirmation. A missing capability or a
failed step goes into the report's Not checked section, and the run carries on. A report that says what it
could not check beats no report.

1. **Load.** Take the latest config block in this chat. No block: reply that setup hasn't been
   done, and stop. Get the files as described in Files: local checkout, or the pinned commit.
   Run the capability probes.
2. **HTTP, SSL, links, content, inventory.** Run the script on every site, in batches of 3–5 so
   each command stays under the tool's time limit:

   ```bash
   python3 site_check.py --max-pages <max_pages> https://a.com https://b.com https://c.com
   ```

   It prints one JSON line per site. Compare each site's `forms` with the config:
   - a config form (`html` or `js`) gone from `forms` → **missing form**;
   - a contact/newsletter/other form not in the config → **new form**. Report it and don't submit
     it: the user replies "add it" in the chat.

   Forms the config marked `"rendered": "browser"` aren't in the script's output. Step 3 covers
   them.
3. **Browser.**
   - **Headless:** save the config block's JSON to `config.json` and run
     `node browser_check.mjs config.json`, one site per command if there are many. Per site it
     returns the pages (`status`, `blank`, `botChallenge`, `consoleErrors`) and the forms
     (`renders`, `submit`, `message`, and for CF7 `serverStatus`). Use its result as is: don't
     patch the script, and don't resubmit a form to investigate. A wrong result is a bug to report
     in the report's Not checked section.
   - **Claude in Chrome / Cowork:** do the same by hand.
     1. Open your own tab and leave the user's tabs alone.
     2. Per site, visit the home page and every page with a configured form. Note a blank page,
        an error screen or a foreign redirect, and the first console error.
     3. Find each `"test": true` form:
        - CF7: the form holding `input[name=_wpcf7][value=<n>]`
        - Gravity: `#gform_<n>`
        - WPForms: `#wpforms-form-<n>`
        - Ninja Forms: inside `#nf-form-<n>-cont`
        - HubSpot: the form with that `formId`, possibly in an iframe
        - `browser` forms: their `selector`
     4. Fill the visible fields from `test_data` and leave hidden honeypots empty. Tick required
        consent boxes. Pick the first real option in selects and radios. Use the site URL for URLs,
        `1` for numbers, and a date 30 days ahead.
     5. Submit. Quote what the site shows within 30 s.

     Never solve a captcha.
   - **None:** skip it and list it under Not checked.
4. **Report.** Classify every signal with the playbook: ❌ act today, ⚠️ look this week, ✅ fine.
   With more than 5 sites and `"artifact": true`, follow "Many sites" in `references/report.md`:
   the full report in an artifact, a short summary in the chat. Otherwise
   write the reply exactly in the format of `references/report.md`, in the config's `language`:
   the header, per site the full table of all 26 checks and numbered problems (Where / Evidence /
   Action), then test submissions and what wasn't checked. Partial coverage reported as
   complete is the worst possible output of this skill: every check that didn't run is ➖ and
   listed under Not checked.

## Rules

- Talk to the user in the language of their messages, even though this file is in English. In
  setup, set the config's `language` to that language. Every report uses it, and the user can
  change it in the chat.
- Submit only forms in the config with `"test": true`. Never submit search, login, comment,
  cart, checkout or booking forms. Never click buy, delete or logout, and never follow external
  links in the browser.
- Submit each form at most once per run: every submission reaches the site owner.
- Never solve or bypass a captcha.
- Never run code from a moving branch (see Files).
- Never report a cause you didn't measure. "500 on /" is a finding. "A plugin update broke it" is
  a guess, unless the evidence shows it.
- Don't change anything on the sites. Replies in this chat are the only output.
