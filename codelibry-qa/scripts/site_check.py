#!/usr/bin/env python3
"""HTTP health check, broken-link crawl and form inventory for a list of sites. Standard library only.

Usage: python3 site_check.py [--max-pages N] URL [URL ...]
Prints one JSON object per site on stdout.
"""
import argparse
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urldefrag, urlparse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 codelibry-qa"
# Share buttons answer 400/302 to a bare GET; they are not links a visitor follows.
SKIP = re.compile(r"facebook\.com/sharer|(twitter|x)\.com/intent|linkedin\.com/(sharing|shareArticle)|pinterest\.[a-z.]+/pin/create|reddit\.com/submit|t\.me/share|api\.whatsapp\.com/send|wa\.me/\?")
# Hosts that refuse bots by design: a 403/429/999 from them says nothing about the link.
BOT_BLOCK = {403, 429, 999}
CAP = 50


PLUGINS = (("cf7", "wpcf7"), ("gravity", "gform"), ("wpforms", "wpforms-form"), ("elementor", "elementor-form"),
           ("mc4wp", "mc4wp-form"), ("fluentform", "fluent"), ("formidable", "frm-show-form"), ("hubspot", "hs-form"),
           ("forminator", "forminator"), ("woocommerce", "woocommerce"))
# Forms a script draws in the browser: no <form> in the HTML, only an embed marker carrying the form's ID.
# (vendor, kind, pattern with the ID in group 1, text that must also be on the page or None)
EMBEDS = [
    ("hubspot", "contact", r"formId[\"']?\s*[:=]\s*[\"']([0-9a-f-]{36})", "hsforms"),
    ("hubspot", "contact", r"data-form-id=[\"']([0-9a-f-]{36})", "hs-form-frame"),
    ("ninja-forms", "contact", r"id=[\"']nf-form-(\d+)-cont", None),
    ("typeform", "contact", r"data-tf-(?:widget|popup|slider|popover|sidetab|live)=[\"']([\w-]+)", None),
    ("typeform", "contact", r"form\.typeform\.com/to/([\w-]+)", "<iframe"),
    ("jotform", "contact", r"(?:jotfor\.ms|jotform\.com)/(?:jsform/)?(\d{10,})", None),
    ("google-forms", "contact", r"docs\.google\.com/forms/d/e/([\w-]+)/viewform\?[^\"']*embedded=true", None),
    ("tally", "contact", r"tally\.so/embed/([\w-]+)", None),
    ("cognito", "contact", r"cognitoforms\.com/f/[\w-]+/(\d+)", None),
    ("zoho-forms", "contact", r"forms\.zohopublic\.[a-z.]+/[\w-]+/form/([\w-]+)", None),
    ("activecampaign", "contact", r"activehosted\.com/f/embed\.php\?id=(\d+)", None),
    ("pipedrive", "contact", r"webforms\.pipedrive\.com/f/([\w-]+)", None),
    ("ms-forms", "contact", r"forms\.office\.com/[^\"']*?[?&]id=([\w-]+)", "<iframe"),
    ("klaviyo", "newsletter", r"klaviyo-form-([\w]+)", None),
    ("calendly", "booking", r"//calendly\.com/([\w-]+(?:/[\w-]+)?)", "calendly-inline-widget"),  # not assets.calendly.com
]


# <link> rels that load a file: fonts and scripts via preload, favicons.
ASSET_RELS = {"stylesheet", "preload", "modulepreload", "icon", "apple-touch-icon"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pages, self.assets, self.forms, self.noindex, self._form = [], [], [], False, None

    def handle_endtag(self, tag):
        if tag == "form" and self._form:
            self.forms.append(self._form)
            self._form = None

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        if tag == "meta" and a.get("name", "").lower() == "robots" and "noindex" in a.get("content", "").lower():
            self.noindex = True
        elif tag == "form":
            self._form = {"id": a.get("id", ""), "class": a.get("class", ""), "action": a.get("action", ""), "role": a.get("role", ""), "fields": []}
        elif self._form is not None and tag in ("input", "textarea", "select"):
            t = (a.get("type") or ("text" if tag == "input" else tag)).lower()
            name = a.get("name", "")
            # Form plugins keep the form's real ID in a hidden field; the <form> tag often has none.
            if t == "hidden" and name in ("_wpcf7", "gform_submit", "wpforms[id]", "form_id") and not self._form["id"]:
                self._form["id"] = f"{name.strip('_[]').split('[')[0]}-{a.get('value', '')}"
            field = f"{t}:{name}"
            if t not in ("hidden", "submit", "button", "reset", "image") and field not in self._form["fields"]:
                self._form["fields"].append(field)
        if tag == "a" and a.get("href"):
            self.pages.append(a["href"])
        elif tag in ("img", "script", "source", "iframe") and a.get("src"):
            self.assets.append(a["src"])
        elif tag == "link" and a.get("href") and set((a.get("rel") or "").lower().split()) & ASSET_RELS:
            self.assets.append(a["href"])


def form_kind(f):
    """(plugin, kind). kind: contact / newsletter / search / login / comment / shop / other."""
    where = f"{f['class']} {f['id']}".lower()
    plugin = next((p for p, key in PLUGINS if key in where), "html")
    fields = " ".join(f["fields"]).lower()
    has_email = "email:" in fields or "mail" in fields
    if f["role"] == "search" or "search" in where or fields in ("text:s", "search:s"):
        return plugin, "search"
    if "password:" in fields or "wp-login" in f["action"]:
        return plugin, "login"
    if f["id"] == "commentform" or "wp-comments-post" in f["action"]:
        return plugin, "comment"
    if plugin == "woocommerce" or re.search(r"cart|checkout|variations_form", where) or "add-to-cart" in fields:
        return plugin, "shop"
    if plugin == "mc4wp" or (has_email and "textarea" not in fields and len(f["fields"]) <= 3):
        return plugin, "newsletter"
    if has_email or "textarea" in fields or plugin != "html":
        return plugin, "contact"
    return plugin, "other"


def embedded_forms(html):
    """[(vendor, kind, id)] for script-rendered forms found by their embed markers."""
    found = []
    for vendor, kind, pattern, guard in EMBEDS:
        if guard and guard not in html:
            continue
        for form_id in re.findall(pattern, html, re.I):
            if (vendor, kind, form_id) not in found:
                found.append((vendor, kind, form_id))
    return found


def robots_blocks_all(origin):
    """True when robots.txt disallows everything for every crawler (a staging robots.txt left after launch)."""
    status, _, text, _, _ = fetch(origin + "/robots.txt")
    if status != 200:
        return False
    agents, in_rules = [], False
    for line in text.splitlines():
        key, _, value = line.split("#")[0].partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value)
        elif key:
            in_rules = True
            if key == "disallow" and value == "/" and "*" in agents:
                return True
    return False


# Editor notes and template filler that reached the live page.
LEFTOVERS = re.compile(r"lorem ipsum|\((?:confirm|todo|tbd|check|fixme)\b[^)]{0,80}\)|\bTODO\b|\bFIXME\b|\[(?:insert|placeholder|add|tbd)[^\]]{0,60}\]|\{\{\s*[\w.]+\s*\}\}|XXX+", re.I)


def leftovers(html):
    text = re.sub(r"<(script|style|noscript|template)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    return list(dict.fromkeys(text[max(m.start() - 60, 0):m.end() + 20].strip() for m in LEFTOVERS.finditer(text)))[:5]


def php_notice(html):
    """PHP warnings printed into the page: WP_DEBUG_DISPLAY is on in production."""
    m = re.search(r"<b>(Warning|Notice|Deprecated)</b>:.{0,300}?on line <b>\d+</b>", html, re.S)
    return re.sub(r"<[^>]+>", "", m.group(0))[:200] if m else None


def fatal(html):
    """WordPress wp_die page (critical error, DB down, stuck maintenance) or raw PHP error output."""
    if 'id="error-page"' in html or "wp-die-message" in html:
        m = re.search(r'wp-die-message[^>]*>(.*?)</div>', html, re.S) or re.search(r"<body[^>]*>(.*?)</body>", html, re.S)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1) if m else "")).strip()[:200] or "wp_die error page"
    m = re.search(r"<b>(Fatal|Parse) error</b>:.{0,300}?on line <b>\d+</b>", html, re.S)
    return re.sub(r"<[^>]+>", "", m.group(0))[:200] if m else None


def fetch(url, method="GET", timeout=20):
    """Returns (status, final_url, body_text, error, headers). Never raises."""
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%~")  # non-ASCII paths, e.g. uploaded file names
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(3_000_000) if method == "GET" else b""
            ctype = r.headers.get("Content-Type", "")
            text = body.decode("utf-8", "replace") if re.search(r"html|xml|text/plain|json", ctype) else ""
            return r.status, r.geturl(), text, None, r.headers
    except urllib.error.HTTPError as e:
        text = e.read(300_000).decode("utf-8", "replace") if method == "GET" else ""
        return e.code, e.geturl() or url, text, None, e.headers
    except Exception as e:  # DNS, TLS, timeout, connection refused
        return None, url, "", f"{type(e).__name__}: {getattr(e, 'reason', e)}"[:200], {}


def check_link(url):
    status, _, _, err, _ = fetch(url, "HEAD", timeout=15)
    if status in (400, 403, 405, 501) or err:  # many servers mishandle HEAD
        status, _, _, err, _ = fetch(url, "GET", timeout=20)
    return url, status, err


def tls_days_left(host):
    """(days, source). Behind an HTTPS proxy the handshake shows the proxy's certificate, so ask the
    public Certificate Transparency log (Cert Spotter, kept current, unlike crt.sh) for the newest
    certificate issued for the host instead."""
    if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
        apex = host.removeprefix("www.")
        status, _, text, err, _ = fetch(f"https://api.certspotter.com/v1/issuances?domain={apex}&expand=dns_names", timeout=40)
        if status != 200:
            return None, f"proxy in the way, Cert Spotter unreachable ({status or err})"
        try:
            ends = [c["not_after"] for c in json.loads(text) if host in c["dns_names"] or "*." + host.split(".", 1)[1] in c["dns_names"]]
        except (ValueError, KeyError, IndexError, TypeError):
            return None, "Cert Spotter answer unreadable"
        if not ends:
            return None, "no valid certificate in Cert Spotter"
        expires = datetime.fromisoformat(max(ends).replace("Z", "+00:00"))
        return (expires - datetime.now(timezone.utc)).days, "Certificate Transparency log (newest issued certificate)"
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as s, ctx.wrap_socket(s, server_hostname=host) as t:
            cert = t.getpeercert()
        expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), timezone.utc)
        issuer = dict(x[0] for x in cert["issuer"]).get("organizationName", "")
        return (expires - datetime.now(timezone.utc)).days, f"TLS handshake, issuer {issuer}"
    except Exception as e:
        return None, f"TLS handshake failed: {type(e).__name__}: {e}"[:200]


def sitemap_urls(origin, limit):
    urls, queue, seen = [], [origin + "/sitemap.xml", origin + "/wp-sitemap.xml"], set()
    while queue and len(urls) < limit and len(seen) < 20:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        status, _, text, _, _ = fetch(sm)
        if status != 200:
            continue
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text):
            (queue if re.search(r"sitemap[^/]*\.xml", loc) else urls).append(loc.replace("&amp;", "&"))
    return urls[:limit]


def clean(base, href):
    href = href.strip()
    if href.startswith(("mailto:", "tel:", "javascript:", "data:", "#", "sms:", "whatsapp:")):
        return None
    url = urldefrag(urljoin(base, href))[0]
    return url if urlparse(url).scheme in ("http", "https") else None


def check_site(start, max_pages):
    t0 = time.time()
    status, final, text, err, headers = fetch(start)
    origin = f"{urlparse(start).scheme}://{urlparse(start).netloc}"
    out = {
        "site": start, "status": status, "error": err, "final_url": final,
        "off_origin": urlparse(final).netloc.removeprefix("www.") != urlparse(start).netloc.removeprefix("www."),
        "ms": int((time.time() - t0) * 1000),
        "fatal": fatal(text),
        "noindex_home": "noindex" in (headers.get("X-Robots-Tag") or "").lower() or bool(re.search(r"<meta[^>]+name=[\"']robots[\"'][^>]+noindex", text, re.I)),
        "robots_blocks_all": robots_blocks_all(origin),
    }
    out["tls_days_left"], out["tls_source"] = tls_days_left(urlparse(start).hostname) if start.startswith("https") else (None, None)
    if status is None or out["off_origin"]:
        return out

    # Crawl same-origin HTML pages (home, then sitemap, then discovered links) and collect every link.
    host = urlparse(final).netloc
    queue = [final] + sitemap_urls(origin, max_pages)
    crawled, found_on, page_errors, notices, mixed, forms, content = set(), {}, [], [], {}, {}, []
    while queue and len(crawled) < max_pages:
        page = queue.pop(0)
        if page in crawled:
            continue
        crawled.add(page)
        p_status, p_final, p_text, p_err, _ = (status, final, text, err, headers) if page == final else fetch(page)
        if p_status is None or p_status >= 400:
            page_errors.append({"url": page, "status": p_status, "error": p_err})
            continue
        if p_text and (f := fatal(p_text)):
            page_errors.append({"url": page, "status": p_status, "fatal": f})
        if p_text and (n := php_notice(p_text)) and len(notices) < 10:
            notices.append({"url": page, "notice": n})
        if p_text and (left := leftovers(p_text)) and len(content) < 20:
            content.append({"url": page, "text": left})
        parser = Page()
        parser.feed(p_text)
        rows = [(*form_kind(f), f["id"], f["fields"], "html") for f in parser.forms]
        rows += [(vendor, kind, form_id, [], "js") for vendor, kind, form_id in embedded_forms(p_text)]
        for plugin, kind, form_id, fields, rendered in rows:
            key = (plugin, form_id, tuple(fields))
            entry = forms.setdefault(key, {"plugin": plugin, "kind": kind, "id": form_id, "rendered": rendered, "fields": fields, "pages": [], "pages_total": 0})
            entry["pages_total"] += 1
            if len(entry["pages"]) < 3:
                entry["pages"].append(page)
        if p_final.startswith("https:"):
            for src in parser.assets:
                if (u := clean(p_final, src)) and u.startswith("http:") and len(mixed) < CAP:
                    mixed.setdefault(u, page)
        for href in parser.pages + parser.assets:
            url = clean(p_final, href)
            if not url or SKIP.search(url):
                continue
            found_on.setdefault(url, [])
            if len(found_on[url]) < 3 and page not in found_on[url]:
                found_on[url].append(page)
            if href in parser.pages and urlparse(url).netloc == host and not re.search(r"\.(pdf|jpe?g|png|gif|webp|svg|zip|docx?|xlsx?|mp4)$|/wp-(admin|login)|/feed/?$|\?", url, re.I):
                queue.append(url)

    to_check = [u for u in found_on if u not in crawled]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(check_link, to_check))
    broken, unverified = [], []
    for url, s, e in results:
        internal = urlparse(url).netloc == host
        if s is not None and s < 400:
            continue
        row = {"url": url, "status": s, "error": e, "internal": internal, "found_on": found_on[url]}
        (unverified if not internal and (s in BOT_BLOCK or (e and "timed out" in e)) else broken).append(row)
    out.update({
        "pages_crawled": len(crawled), "links_checked": len(to_check),
        "page_errors": [dict(e, found_on=found_on.get(e["url"], [])) for e in page_errors[:CAP]], "broken_links": broken[:CAP], "broken_total": len(broken),
        "unverified_links": unverified[:CAP],
        "php_notices": notices,
        "content_leftovers": content,
        "mixed_content": [{"url": u, "found_on": p} for u, p in mixed.items()],
        "forms": sorted(forms.values(), key=lambda f: (f["kind"], -f["pages_total"])),
    })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=100)
    ap.add_argument("urls", nargs="+")
    args = ap.parse_args()
    for url in args.urls:
        url = url if "://" in url else "https://" + url
        try:
            print(json.dumps(check_site(url, args.max_pages), ensure_ascii=False), flush=True)
        except Exception as e:
            print(json.dumps({"site": url, "error": f"check crashed: {e}"[:300]}), flush=True)


if __name__ == "__main__":
    sys.exit(main())
