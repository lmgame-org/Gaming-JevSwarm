"""LMGame branding for every page's <head>: icons and link-preview tags, set up the same way as the WMEval blog
(absolute, versioned URLs; a 1200x630 LMGame card for previews; an inline 32px icon as a last resort)."""
import base64
import hashlib
import html
import os

BASE = "https://snyhlx.github.io/the_irregulars_detective_game/"
SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")


def _v(rel):
    return hashlib.sha1(open(os.path.join(SITE, rel), "rb").read()).hexdigest()[:10]


def _url(rel):
    return f"{BASE}{rel}?v={_v(rel)}"


def icons():
    b64 = base64.b64encode(open(os.path.join(SITE, "assets/brand/lmgame-icon-32.png"), "rb").read()).decode()
    return (f'<link rel="icon" type="image/png" sizes="192x192" href="{_url("assets/brand/lmgame-icon-192.png")}">'
            f'<link rel="icon" type="image/png" sizes="32x32" href="{_url("assets/brand/lmgame-icon-32.png")}">'
            f'<link rel="icon" type="image/png" sizes="16x16" href="{_url("assets/brand/lmgame-icon-16.png")}">'
            f'<link rel="shortcut icon" type="image/x-icon" href="{BASE}lmgame-favicon.ico">'
            f'<link rel="apple-touch-icon" sizes="180x180" href="{_url("assets/brand/lmgame-icon-180.png")}">'
            f'<link rel="icon" type="image/png" sizes="32x32" href="data:image/png;base64,{b64}">')


def social(title, desc, page):
    t, d = html.escape(title, quote=True), html.escape(desc, quote=True)
    card = _url("assets/brand/lmgame-card-1200x630.png")
    return (f'<link rel="image_src" href="{card}"><meta itemprop="image" content="{card}">'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="LMGame">'
            f'<meta name="application-name" content="LMGame"><meta name="apple-mobile-web-app-title" content="LMGame">'
            f'<meta property="og:url" content="{BASE}{page}"><meta property="og:title" content="{t}">'
            f'<meta property="og:description" content="{d}"><meta property="og:image" content="{card}">'
            f'<meta property="og:image:secure_url" content="{card}"><meta property="og:image:type" content="image/png">'
            f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            f'<meta property="og:image:alt" content="LMGAME gamepad logo"><meta name="twitter:card" content="summary_large_image">'
            f'<meta name="twitter:title" content="{t}"><meta name="twitter:description" content="{d}">'
            f'<meta name="twitter:image" content="{card}"><meta name="twitter:image:alt" content="LMGAME gamepad logo">')
