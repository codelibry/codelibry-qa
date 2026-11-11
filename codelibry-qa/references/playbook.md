# Playbook — signal → severity → what to do

Field names in backticks are from `site_check.py` output. The other signals come from the browser
pass. ❌ = act today, ⚠️ = look this week, ✅ = fine, not listed as a problem. Use the reaction text in the
report, shortened, and translated into the report language.

## Site up

| Signal | Severity | Reaction |
|---|---|---|
| `error` with a DNS failure (`Name or service not known`, `getaddrinfo`) | ❌ | Domain or DNS: check domain expiry and the DNS zone at the registrar. |
| `error` with timeout / connection refused / reset | ❌ | Server down or overloaded: check the hosting status page and panel, contact the host. |
| `status` 500–599 | ❌ | Server or PHP error: read the PHP error log in the hosting panel. Check what auto-updated overnight (plugins, core, PHP version). |
| `fatal` / `page_errors[].fatal` "critical error on this website" | ❌ | WordPress fatal: the admin got a recovery-mode email. Find the plugin in the error log and disable it by renaming its folder over SFTP. |
| `fatal` "Error establishing a database connection" | ❌ | Database down or credentials changed: check the DB server in the hosting panel and `wp-config.php`. |
| `fatal` "Briefly unavailable for scheduled maintenance" | ❌ | Update got stuck: delete `.maintenance` in the WordPress root, then finish the update. |
| `fatal` "Fatal error … on line N" / "Parse error" | ❌ | PHP error shown publicly: fix the file named in the message, and turn off `WP_DEBUG_DISPLAY`. |
| `noindex_home: true` | ❌ | The home page tells search engines not to index it (meta robots or `X-Robots-Tag`), often left over from staging. Settings → Reading → uncheck "Discourage search engines", check the SEO plugin. |
| `robots_blocks_all: true` | ❌ | `robots.txt` has `Disallow: /` for every crawler: the whole site is blocked from search. Fix `robots.txt` (file in the web root or the SEO plugin). |
| `php_notices` not empty | ⚠️ | PHP warnings are printed on public pages: `WP_DEBUG_DISPLAY` is on. Set it to `false` in `wp-config.php` and fix the warning named. |
| `off_origin: true` | ❌ | Site redirects to another domain: possible hack or expired hosting. Open it in a browser and check `.htaccess`, the `siteurl` / `home` options, and recently changed files. |
| `status` 403 / 429 / 503 on the home page | ⚠️ | WAF or CDN blocks the monitor. If the browser pass loads the site fine, mention it once and move on. If the browser is blocked too, ❌. |
| `ms` > 10000 | ⚠️ | Slow first response: check page cache and hosting resource limits. |
| `tls_days_left` < 14 | ⚠️ | Certificate expires soon: check auto-renewal (hosting panel, Let's Encrypt). Below 3 days, or negative: ❌. With `tls_source` "Certificate Transparency log", it's the newest certificate *issued*: if the site still serves an older one, the renewal didn't get installed. |
| `tls_days_left` null, `tls_source` "TLS handshake failed" | ⚠️ | TLS failed from the checker. If the browser loads the site over https fine, it's the checker's network: say so under Not checked, not as a site problem. |
| `tls_days_left` null, `tls_source` about a proxy or Cert Spotter | ✅ | SSL not checked this run: say so under Not checked. |

## Broken links

| Signal | Severity | Reaction |
|---|---|---|
| `page_errors` 404 for a page that the menu or many pages link to (several `found_on`) | ❌ | A page people navigate to is gone: restore it or add a 301 redirect. Name the linking pages. |
| `page_errors` 404/410 elsewhere | ⚠️ | Internal page gone: add a 301 redirect, or fix the link on the `found_on` pages. |
| `page_errors` 5xx | ❌ | Some pages throw server errors: read the PHP error log for that URL. |
| `broken_links` internal asset (`.css`, `.js`) | ❌ | Layout or scripts broken: purge the cache plugin and CDN. Check the last deploy shipped its files. |
| `broken_links` internal image, font, favicon or file | ⚠️ | Missing media or theme file (a font in `assets/fonts/` usually means a theme deploy or cleanup): re-upload, or remove the reference on the `found_on` pages. |
| `broken_links` external, status 404/410 or DNS error | ⚠️ | Outbound link dead: update or remove it on the `found_on` pages. |
| `mixed_content` not empty | ⚠️ | An https page loads files over `http://`: browsers block them or show "not secure". Replace the URLs (Better Search Replace `http://domain` → `https://domain`). |
| `unverified_links` (403/429/999, timeouts on social and big platforms) | ✅ | The host blocks bots. Not proof of a dead link. Mention the count under Not checked only. |

## Content

| Signal | Severity | Reaction |
|---|---|---|
| `content_leftovers` (editor notes like "(confirm: …)", TODO, lorem ipsum, `{{placeholder}}`) | ⚠️ | Visitors see internal notes or filler text. Quote it with its page. Remove it in the page editor. |

## Browser pass

| Signal | Severity | Reaction |
|---|---|---|
| `blank: true`, or an error screen in the browser while HTTP said 200 | ❌ | Front-end broken: a JS error or missing CSS. Quote the console error, purge caches. |
| Console errors from the site's own scripts (`Uncaught …`) | ⚠️ | JS error: quote the first message. A script that loads before its dependency usually means a plugin or cache/minify update. Purge cache, test with minify off. ❌ on a form page. |
| `botChallenge: true`: the CDN's "Checking your browser" page didn't clear in 20 s | ⚠️ (Not checked) | The page and its forms weren't checked this run. If it repeats, allowlist the monitor in the CDN/WAF or test those forms by hand. |
| Console noise: third-party analytics, ad or chat scripts, "violates … report-only Content Security Policy", favicon 404 | ✅ | Ignore. |

## Forms

| Signal | Severity | Reaction |
|---|---|---|
| Missing form: in the config, not found on the site any more | ❌ | Form plugin deactivated, shortcode or block removed, or the page changed. Check the page in the editor. Visitors can't contact the client. |
| `renders: false` / `submit: "form not found or not drawn"`: the form, or for `rendered: js` its embed marker, is on the page, but it never draws in the browser | ❌ | The form's script is blocked (cookie banner, CSP, ad blocker) or the form was deleted or unpublished in the vendor's account (HubSpot, Typeform, …). Open the page and check the console, then the form in the vendor dashboard. |
| New form: on the site, not in the config | ⚠️ | Not tested yet. List it; the user replies "add it" in the chat. |
| `submit: "sent"` or `"sent (redirected)"` | ✅ | Nothing to report. The email to the client isn't checked. |
| `serverStatus: "mail_failed"` (CF7), or a GF / WPForms mail error | ❌ | The site couldn't send this form's mail (`wp_mail` failed). If another form on the same site sent fine, check this form's Mail tab (To, From, extra headers); otherwise the SMTP plugin's log and the provider's quota or API key. |
| `serverStatus` `validation_failed` / `acceptance_missing`, or a validation error on a field the test data should satisfy | ⚠️ | Field rules changed or the form is broken. Quote the message, try the form by hand. |
| `serverStatus: "spam"`, or a spam/captcha rejection after submit ("spam", "captcha failed") | ⚠️ | The form rejected a real-browser submission. Real visitors may hit it too. Try the form by hand, check the captcha keys in the form plugin. |
| `submit: "captcha challenge: needs a human"` | ⚠️ | Needs a human: the monitor doesn't solve captchas. Test the form by hand this week. |
| `submit: "no result in 30s"` | ❌ | Submit hangs: check the console and network for the form's AJAX request (500 = PHP error on submit). |
| `submit: "not automated: form hidden on load (popup or closed tab)"` / `"submit button hidden (multi-step form)"` | ✅ | Found and rendered, not submitted. Note it under Not checked: test it by hand now and then. |
| `submit: "skipped: required file upload"` | ✅ | Monitor limitation: note it under Not checked. Set `"test": false` for that form or test it by hand. |
| `submit: "not automated: vendor-hosted form in an iframe"` (Typeform, Google Forms, Jotform, …) | ✅ | Only rendering is checked. Note it under Not checked: test it by hand now and then. |
| `submit: "not tested: no test_data in config"` | ⚠️ (Not checked) | Setup didn't collect test data: ask for it in the chat. |
