"""Runs site_check.py against a local fake site. python3 -m unittest discover tests"""
import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

SCRIPT = Path(__file__).parent.parent / "codelibry-qa" / "scripts" / "site_check.py"
PAGES = {
    "/": '<a href="/about/">About</a> <a href="/gone/">Gone</a> <a href="/blog/">Blog</a> <a href="mailto:x@y.z">mail</a>'
         '<img src="/missing.png"> <link rel="preload" href="/fonts/gone.woff2" as="font"> <a href="http://no-such-host.invalid/">dead</a>'
         '<meta name="robots" content="noindex,nofollow">'
         '<form role="search"><input name="s"></form>'
         '<form class="wpcf7-form" id="wpcf7-f5"><input name="your-name"><input type="email" name="your-email">'
         '<textarea name="msg"></textarea><input type="hidden" name="_wpcf7" value="5"></form>',
    "/about/": '<p>About</p><a href="/">Home</a><p>Price on request (confirm: public)</p>'
               '<script>// TODO not visible</script>'
               '<script src="//js.hsforms.net/forms/embed/v2.js"></script><script>hbspt.forms.create({portalId: "123",'
               ' formId: "0f1e2d3c-4b5a-6978-8091-a2b3c4d5e6f7"});</script><div id="nf-form-3-cont" class="nf-form-cont"></div>'
               '<script>var w = "https://assets.calendly.com/assets/external/widget.js"</script>'
               '<div class="calendly-inline-widget" data-url="https://calendly.com/acme/intro"></div><br /><b>Warning</b>:  Undefined variable $x in <b>/www/a.php</b> on line <b>3</b>',
    "/robots.txt": "User-agent: *\nDisallow: /\n",
    "/sitemap.xml": "<urlset><url><loc>{origin}/hidden/</loc></url></urlset>",
    "/hidden/": '<body id="error-page"><div class="wp-die-message"><p>There has been a critical error on this website.</p></div></body>',
    "/blog/": "<p>How to fix There has been a critical error on this website</p>"
              '<a href="https://www.facebook.com/sharer/sharer.php?u=x">share</a> <img src="/фото—1.png">',
    "/фото—1.png": "png",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(unquote(self.path))
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "application/xml" if self.path.endswith(".xml") else "text/plain" if self.path.endswith(".txt") else "text/html")
        self.end_headers()
        if body:
            self.wfile.write(body.replace("{origin}", ORIGIN).encode())

    do_HEAD = do_GET

    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
ORIGIN = f"http://127.0.0.1:{server.server_port}"
threading.Thread(target=server.serve_forever, daemon=True).start()


class SiteCheck(unittest.TestCase):
    def test_finds_broken_links_and_fatals(self):
        out = subprocess.run([sys.executable, str(SCRIPT), ORIGIN + "/"], capture_output=True, text=True, timeout=120)
        r = json.loads(out.stdout)
        self.assertEqual(r["status"], 200)
        self.assertFalse(r["off_origin"])
        self.assertIsNone(r["fatal"])
        self.assertTrue(r["noindex_home"])
        self.assertTrue(r["robots_blocks_all"])
        kinds = [(f["plugin"], f["kind"], f["id"], f["rendered"]) for f in r["forms"]]
        self.assertEqual(kinds, [
            ("calendly", "booking", "acme/intro", "js"),
            ("cf7", "contact", "wpcf7-f5", "html"),
            ("hubspot", "contact", "0f1e2d3c-4b5a-6978-8091-a2b3c4d5e6f7", "js"),
            ("ninja-forms", "contact", "3", "js"),
            ("html", "search", "", "html"),
        ])
        self.assertEqual(r["forms"][1]["fields"], ["text:your-name", "email:your-email", "textarea:msg"])
        self.assertIn("Undefined variable", r["php_notices"][0]["notice"])
        self.assertEqual([c["url"] for c in r["content_leftovers"]], [ORIGIN + "/about/"])
        self.assertIn("(confirm: public)", r["content_leftovers"][0]["text"][0])
        self.assertEqual(len(r["content_leftovers"][0]["text"]), 1, "TODO inside <script> is not visible text")
        self.assertEqual(r["pages_crawled"], 5)  # /, /about/, /gone/ (404), /blog/, /hidden/ from the sitemap
        broken = {b["url"]: b for b in r["broken_links"]}
        self.assertEqual(broken[ORIGIN + "/missing.png"]["status"], 404)
        self.assertEqual(broken[ORIGIN + "/fonts/gone.woff2"]["status"], 404, "preloaded font checked")
        self.assertIsNotNone(broken["http://no-such-host.invalid/"]["error"])
        self.assertNotIn("mailto:x@y.z", broken)
        errors = {e["url"]: e for e in r["page_errors"]}
        self.assertEqual(errors[ORIGIN + "/gone/"]["status"], 404)
        self.assertEqual(errors[ORIGIN + "/gone/"]["found_on"], [ORIGIN + "/"])
        self.assertIn("critical error", errors[ORIGIN + "/hidden/"]["fatal"])
        self.assertNotIn(ORIGIN + "/blog/", errors, "an article quoting the message is not a fatal")
        self.assertFalse([u for u in broken if "facebook" in u or "png" in u and "missing" not in u], broken)


if __name__ == "__main__":
    unittest.main()
