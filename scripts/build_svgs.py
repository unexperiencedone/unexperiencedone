"""Builds the animated manga-ink SVGs used by the profile README.

Styling mirrors https://aakshantkumar.vercel.app : paper / ink / spot pink,
Rozha One + Amita + Mukta, ink-stroke reveals and "editor's circle" proofs.

Fonts are subset per SVG and embedded as base64 WOFF so they render inside
GitHub's <img> sandbox (which can't fetch web fonts).

    python scripts/build_svgs.py            # writes assets/*.svg
"""
from __future__ import annotations

import base64
import html
import io
import math
import random
import re
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONT_DIR = Path(__file__).resolve().parent / ".fonts"

PAPER, PAPER2, INK, INK2, GUIDE, SPOT = "#f5f5f2", "#e9e9e4", "#0d0d0d", "#3b3b3b", "#a9c8e8", "#ff1f6f"
EASE_INK = "cubic-bezier(.7,0,.2,1)"
EASE_SETTLE = "cubic-bezier(.22,1,.36,1)"

FONTS = {  # family alias -> google/fonts path
    "Rozha": "rozhaone/RozhaOne-Regular.ttf",
    "Amita": "amita/Amita-Regular.ttf",
    "Mukta": "mukta/Mukta-Regular.ttf",
    "MuktaB": "mukta/Mukta-Bold.ttf",
    "MuktaX": "mukta/Mukta-ExtraBold.ttf",
}
MONO = "'JetBrains Mono','Cascadia Code',Consolas,'Courier New',monospace"

random.seed(7)


# ---------------------------------------------------------------- fonts

def _font_path(alias: str) -> Path:
    rel = FONTS[alias]
    p = FONT_DIR / Path(rel).name
    if not p.exists():
        FONT_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(f"https://github.com/google/fonts/raw/main/ofl/{rel}", p)
    return p


def font_face(alias: str, text: str) -> str:
    opts = subset.Options()
    # just the shaping Devanagari needs (conjuncts, half forms, matras) + Latin basics
    opts.layout_features = ["ccmp", "locl", "nukt", "akhn", "rphf", "rkrf", "pref", "blwf", "half", "pstf",
                            "vatu", "cjct", "init", "pres", "abvs", "blws", "psts", "haln", "calt",
                            "kern", "mark", "mkmk", "abvm", "blwm", "dist", "liga"]
    opts.flavor = "woff"
    opts.name_IDs = []
    opts.notdef_outline = True
    opts.hinting = False  # browsers rasterise fine without TT hints; big size win
    font = TTFont(_font_path(alias))
    sub = subset.Subsetter(opts)
    sub.populate(text=text + " .")
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff"
    font.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:'{alias}';src:url(data:font/woff;base64,{b64}) format('woff');}}"


def svg_doc(w: int, h: int, label: str, css: str, body: str) -> str:
    """Wraps body, embedding a subset of each font family referenced by a class."""
    texts = " ".join(html.unescape(t) for t in re.findall(r">([^<>]+)<", body))
    faces = [font_face(a, texts) for a in FONTS if re.search(rf"\b{a.lower()}\b", body)]
    base = f"""
    .rozha{{font-family:'Rozha',serif}} .amita{{font-family:'Amita',cursive}}
    .mukta{{font-family:'Mukta',sans-serif}} .muktab{{font-family:'MuktaB',sans-serif}}
    .muktax{{font-family:'MuktaX',sans-serif}} .mono{{font-family:{MONO}}}
    .draw{{stroke-dasharray:1;stroke-dashoffset:1}}
    """
    reduced = "@media (prefers-reduced-motion: reduce){*{animation:none!important}.rm-show{opacity:1!important;transform:none!important}.draw{stroke-dashoffset:0!important}.rm-hide{display:none}}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(label)}">\n'
        f"<style>{''.join(faces)}{base}{css}{reduced}</style>\n{body}\n</svg>\n"
    )


# ---------------------------------------------------------------- shared bits

def halftone(pid: str, r: float = 1.6, step: int = 9, color: str = INK) -> str:
    return (f'<pattern id="{pid}" width="{step}" height="{step}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<circle cx="{step/2}" cy="{step/2}" r="{r}" fill="{color}"/></pattern>')


def poly(points) -> str:
    return " ".join(f"{x},{y}" for x, y in points)


def poly_path(points) -> str:
    return "M" + " L".join(f"{x} {y}" for x, y in points) + " Z"


def focus_lines(cx: float, cy: float, n: int, r_in: float, r_out: float, jitter: float = 0.0) -> str:
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n + random.uniform(-jitter, jitter)
        w = random.uniform(0.006, 0.02)
        ri = r_in * random.uniform(0.85, 1.25)
        p = [(cx + ri * math.cos(a), cy + ri * math.sin(a)),
             (cx + r_out * math.cos(a - w), cy + r_out * math.sin(a - w)),
             (cx + r_out * math.cos(a + w), cy + r_out * math.sin(a + w))]
        out.append(f'<polygon points="{poly((round(x, 1), round(y, 1)) for x, y in p)}"/>')
    return "".join(out)


def editors_circle(cx: float, cy: float, rx: float, ry: float, cls: str, delay: float) -> str:
    """A wobbly, slightly-overshooting hand-drawn loop, like an editor's red pen."""
    pts = []
    for i in range(0, 380, 10):
        t = math.radians(i - 20)
        wob = 1 + 0.05 * math.sin(3 * t) + 0.03 * math.cos(5 * t)
        pts.append((cx + rx * wob * math.cos(t) * (1 + i / 3000), cy + ry * wob * math.sin(t)))
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    return (f'<path class="draw {cls}" pathLength="1" d="{d}" fill="none" stroke="{SPOT}" stroke-width="3.2" '
            f'stroke-linecap="round" stroke-linejoin="round" style="animation-delay:{delay}s"/>')


# ---------------------------------------------------------------- cover

def cover() -> str:
    W, H = 1200, 480
    pA = [(24, 24), (742, 24), (706, 456), (24, 456)]
    pB = [(758, 24), (1176, 24), (1176, 232), (740, 232)]
    pC = [(739, 248), (1176, 248), (1176, 456), (722, 456)]

    roles = [
        ("ML Engineer", "मशीन लर्निंग इंजीनियर"),
        ("Full-Stack Builder", "मॉडल से प्रोडक्ट तक"),
        ("Co-founder · VP Tech", "सह-संस्थापक · Kaiketsu Tech"),
        ("Edge-AI Researcher", "शोध · affective computing"),
    ]
    period, start = 3.2, 2.6
    cycle = period * len(roles)
    role_css = "".join(
        f".role{i}{{animation:roleSwap {cycle}s steps(1) {start + i * period + 0.32:.2f}s infinite}}" for i in range(len(roles)))
    role_pct = 100 / len(roles)

    css = f"""
    .panel{{animation:draw 1s {EASE_INK} forwards}}
    @keyframes draw{{to{{stroke-dashoffset:0}}}}
    .name{{fill:transparent;stroke:{INK};stroke-width:1.4;stroke-dasharray:1400;stroke-dashoffset:1400;
      animation:ink 2.4s cubic-bezier(.35,.1,.25,1) .5s forwards,inkFill .6s ease 2s forwards}}
    @keyframes ink{{to{{stroke-dashoffset:0}}}}
    @keyframes inkFill{{to{{fill:{INK};stroke-width:.3}}}}
    .rise{{opacity:0;animation:rise .8s {EASE_SETTLE} forwards}}
    @keyframes rise{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}
    .track{{opacity:0;animation:track 1s {EASE_SETTLE} 1.7s forwards}}
    @keyframes track{{from{{opacity:0;letter-spacing:28px}}to{{opacity:1;letter-spacing:9px}}}}
    .sfx{{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .55s cubic-bezier(.34,1.8,.5,1) 2.2s forwards}}
    @keyframes pop{{0%{{opacity:0;transform:scale(2.4) rotate(-26deg)}}100%{{opacity:1;transform:scale(1) rotate(-8deg)}}}}
    .flA{{animation:flick .28s steps(1) infinite}} .flB{{animation:flick .28s steps(1) .14s infinite}}
    @keyframes flick{{50%{{opacity:0}}}}
    .bubble{{opacity:0;transform-box:fill-box;transform-origin:20% 100%;animation:bub .5s cubic-bezier(.34,1.6,.5,1) 2.4s forwards}}
    @keyframes bub{{from{{opacity:0;transform:scale(.6)}}to{{opacity:1;transform:none}}}}
    .wipe{{animation:wipe {period}s {EASE_INK} {start}s infinite both}}
    @keyframes wipe{{0%{{transform:translateX(-420px)}}10%{{transform:translateX(0)}}20%,100%{{transform:translateX(420px)}}}}
    .role{{opacity:0}} {role_css}
    @keyframes roleSwap{{0%{{opacity:1}}{role_pct:.2f}%{{opacity:0}}100%{{opacity:0}}}}
    .caret{{animation:flick 1s steps(1) infinite}}
    .tone{{opacity:0;animation:fade 1s ease 1.2s forwards}}
    @keyframes fade{{to{{opacity:1}}}}
    """

    bubble_path = ("M800 300 Q800 274 830 274 L1120 274 Q1150 274 1150 300 L1150 382 Q1150 408 1120 408 "
                   "L880 408 L842 438 L852 408 L830 408 Q800 408 800 382 Z")
    roles_svg = "".join(
        f'<g class="role role{i}"><text class="muktax" x="975" y="334" text-anchor="middle" font-size="27" fill="{INK}">{html.escape(en)}</text>'
        f'<text class="amita" x="975" y="374" text-anchor="middle" font-size="19" fill="{SPOT}">{html.escape(hi)}</text></g>'
        for i, (en, hi) in enumerate(roles))

    chips = [("CSE (AI) · CSJMU '28", 188), ("VP Tech · Kaiketsu Tech", 198), ("Founder · Void Walkers", 192)]
    cx, chip_svg = 58, ""
    for i, (t, w) in enumerate(chips):
        chip_svg += (f'<g class="rise" style="animation-delay:{2.6 + i * 0.12:.2f}s"><rect x="{cx}" y="384" width="{w}" height="34" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>'
                     f'<text class="muktab" x="{cx + w / 2}" y="407" text-anchor="middle" font-size="15" fill="{INK}" dominant-baseline="middle">{html.escape(t)}</text></g>')
        cx += w + 14

    flA = focus_lines(958, 128, 70, 70, 330, 0.03)
    flB = focus_lines(958, 128, 70, 64, 330, 0.03)

    body = f"""
<defs>
  {halftone('ht', 1.7, 8)}
  <linearGradient id="fadeR" gradientUnits="userSpaceOnUse" x1="300" y1="0" x2="760" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>
  <linearGradient id="fadeB" x1="0" y1="0" x2="0" y2="1"><stop offset=".25" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".9"/></linearGradient>
  <mask id="mR"><rect x="0" y="0" width="{W}" height="{H}" fill="url(#fadeR)"/></mask>
  <mask id="mB"><rect x="0" y="0" width="{W}" height="{H}" fill="url(#fadeB)"/></mask>
  <clipPath id="cA"><polygon points="{poly(pA)}"/></clipPath>
  <clipPath id="cB"><polygon points="{poly(pB)}"/></clipPath>
  <clipPath id="cC"><polygon points="{poly(pC)}"/></clipPath>
  <clipPath id="cBub"><path d="{bubble_path}"/></clipPath>
</defs>
<rect width="{W}" height="{H}" fill="{PAPER}"/>

<!-- panel A : the name -->
<g clip-path="url(#cA)">
  <rect class="tone" x="24" y="24" width="740" height="440" fill="url(#ht)" opacity=".2" mask="url(#mR)"/>
  <text class="mono rise" x="58" y="70" font-size="14" fill="{INK2}" style="animation-delay:.3s">p. 01 / GitHub · <tspan fill="{SPOT}">आरंभ!</tspan><tspan class="caret" fill="{SPOT}"> ▌</tspan></text>
  <text class="rozha name" x="52" y="198" font-size="104">आक्षांत कुमार</text>
  <text class="muktax track" x="58" y="250" font-size="26" fill="{INK}">AAKSHANT KUMAR</text>
  <text class="amita rise" x="58" y="304" font-size="25" fill="{SPOT}" style="animation-delay:2.1s">मॉडल की ट्रेनिंग से प्रोडक्ट की शिपिंग तक।</text>
  <text class="mukta rise" x="58" y="346" font-size="21" fill="{INK2}" style="animation-delay:2.3s">I train models and ship the products around them.</text>
  {chip_svg}
</g>
<path class="draw panel" pathLength="1" d="{poly_path(pA)}" fill="none" stroke="{INK}" stroke-width="4.5" stroke-linejoin="miter"/>

<!-- panel B : focus lines + SFX -->
<g clip-path="url(#cB)">
  <rect x="700" y="0" width="500" height="260" fill="{PAPER}"/>
  <g fill="{INK}" class="flA">{flA}</g>
  <g fill="{INK}" class="flB" opacity=".9">{flB}</g>
  <ellipse cx="958" cy="128" rx="120" ry="70" fill="{PAPER}"/>
  <g class="sfx"><text class="rozha" x="958" y="156" text-anchor="middle" font-size="88" fill="{SPOT}" stroke="{INK}" stroke-width="5" paint-order="stroke" stroke-linejoin="round">आरंभ!</text></g>
</g>
<path class="draw panel" pathLength="1" d="{poly_path(pB)}" fill="none" stroke="{INK}" stroke-width="4.5" style="animation-delay:.25s"/>

<!-- panel C : speech bubble cycling roles with an ink wipe -->
<g clip-path="url(#cC)">
  <rect class="tone" x="700" y="248" width="500" height="220" fill="url(#ht)" opacity=".22" mask="url(#mB)"/>
  <g class="rise" style="animation-delay:2.2s">
    <rect x="990" y="418" width="172" height="26" fill="{PAPER2}" stroke="{INK}" stroke-width="2"/>
    <text class="muktab" x="1076" y="436" text-anchor="middle" font-size="13" fill="{INK}">Kanpur, IN · कानपुर से</text>
  </g>
  <g class="bubble">
    <path d="{bubble_path}" fill="{PAPER}" stroke="{INK}" stroke-width="3.5" stroke-linejoin="round"/>
    <g clip-path="url(#cBub)">
      {roles_svg}
      <rect class="wipe" x="796" y="268" width="360" height="146" fill="{INK}"/>
    </g>
  </g>
</g>
<path class="draw panel" pathLength="1" d="{poly_path(pC)}" fill="none" stroke="{INK}" stroke-width="4.5" style="animation-delay:.5s"/>
"""
    return svg_doc(W, H, "Aakshant Kumar — ML Engineer & Builder", css, body)


# ---------------------------------------------------------------- section title strips

def header(en: str, hi: str, sub: str, page: str) -> str:
    W, H = 1200, 112
    slab = [(0, 14), (460, 14), (430, 98), (0, 98)]
    css = f"""
    .slab{{transform:translateX(-480px);animation:slab .75s {EASE_INK} .1s forwards}}
    @keyframes slab{{to{{transform:none}}}}
    .en{{opacity:0;animation:en .6s {EASE_SETTLE} .55s forwards}}
    @keyframes en{{from{{opacity:0;letter-spacing:22px}}to{{opacity:1;letter-spacing:6px}}}}
    .hiw{{transform:translateX(-520px);animation:slab .8s {EASE_INK} .7s forwards}}
    .brush{{animation:draw .6s {EASE_INK} 1.35s forwards}}
    @keyframes draw{{to{{stroke-dashoffset:0}}}}
    .meta{{opacity:0;animation:fade .6s ease 1.5s forwards}}
    @keyframes fade{{to{{opacity:1}}}}
    .tick{{animation:tick 2.4s {EASE_INK} 2s infinite}}
    @keyframes tick{{0%,100%{{transform:none}}50%{{transform:translateX(6px)}}}}
    """
    brush = "M482 86 C540 80 600 92 660 84 S760 80 800 86"
    body = f"""
<defs><clipPath id="hiClip"><rect class="hiw" x="470" y="0" width="520" height="{H}"/></clipPath>{halftone('ht', 1.4, 7)}</defs>
<rect width="{W}" height="{H}" fill="{PAPER}"/>
<rect x="2" y="2" width="{W - 4}" height="{H - 4}" fill="none" stroke="{INK}" stroke-width="4"/>
<g class="slab">
  <polygon points="{poly(slab)}" fill="{INK}"/>
  <polygon points="{poly([(380, 14), (460, 14), (430, 98), (350, 98)])}" fill="url(#ht)" opacity=".0"/>
</g>
<text class="muktax en rm-show" x="36" y="70" font-size="34" fill="{PAPER}">{html.escape(en.upper())}</text>
<g clip-path="url(#hiClip)"><text class="rozha" x="484" y="72" font-size="50" fill="{SPOT}">{html.escape(hi)}</text></g>
<path class="draw brush" pathLength="1" d="{brush}" fill="none" stroke="{INK}" stroke-width="4" stroke-linecap="round"/>
<g class="meta rm-show">
  <text class="mono" x="1166" y="44" text-anchor="end" font-size="14" fill="{INK2}">{html.escape(page)} <tspan class="tick" fill="{SPOT}">→</tspan></text>
  <text class="mukta" x="1166" y="78" text-anchor="end" font-size="18" fill="{INK2}">{html.escape(sub)}</text>
</g>
"""
    return svg_doc(W, H, f"{en} · {hi}", css, body)


# ---------------------------------------------------------------- arcs spread

ARCS = [
    dict(n="1", hi_n="पर्व १", title="Origin Arc", hi="आरंभ पर्व", when="Late 2024 – Late 2025 · foundations",
         eps=["Onto campus: B.Tech CSE (AI), CSJM University, Kanpur",
              "Data Viz Analyst intern @ Excelerate: Looker, pandas, SQL",
              "First agent: Snake AI, a Deep Q-Network from scratch",
              "Indian Railways crowd-level model, 95.8% accuracy"],
         unlocked=["Python", "pandas", "SQL", "DQN"], proof="DQN ✓"),
    dict(n="2", hi_n="पर्व २", title="Party Arc", hi="दल पर्व", when="Early 2026 · architecture & rapid prototyping",
         eps=["Robo Rumble 3.0 official site: most commits of anyone",
              "Rise UP Public School: 81 endpoints, 7 roles, Razorpay",
              "Formed Void Walkers, the hackathon squad",
              "Smart Home Ear: PyTorch CNN on ESC-50 audio"],
         unlocked=["Next.js", "React 19", "TypeScript", "PyTorch"], proof="113 / 292"),
    dict(n="3", hi_n="पर्व ३", title="Awakening Arc", hi="जागरण पर्व", when="Spring – Mid 2026 · domain AI & multimodal",
         eps=["VedaVoice: Hinglish voice-to-ledger, DistilBERT NER",
              "AirGated: offline, un-spoofable attendance",
              "CSJMU Student Assistant: RAG over pgvector",
              "Propely: LightGBM + conformal demand forecasts",
              "Co-founded Kaiketsu Tech as VP Tech"],
         unlocked=["DistilBERT NER", "Groq", "pgvector", "LightGBM"], proof="Finalist"),
    dict(n="4", hi_n="पर्व ४", title="Horizon Arc", hi="क्षितिज पर्व", when="Late 2026 · ongoing · जारी",
         eps=["Nova: a local voice OS, 658 tests, six-tier cascade",
              "Drishtikon: VLM for satellite imagery, SIH 2026",
              "CivicPulse: jurisdiction-registry routing, BwB 2.0",
              "Edge emotion: int8 multimodal fusion on-device",
              "Exoplanets: TESS light curves, TLS + PyTorch"],
         unlocked=["VLMs", "Agents", "TinyML", "three.js"], proof="ongoing"),
]


def arcs() -> str:
    W, H = 1200, 780
    panels = [
        [(24, 24), (612, 24), (592, 382), (24, 382)],
        [(628, 24), (1176, 24), (1176, 382), (608, 382)],
        [(24, 398), (590, 398), (570, 756), (24, 756)],
        [(606, 398), (1176, 398), (1176, 756), (586, 756)],
    ]
    css = f"""
    .cover{{animation:uncover .9s {EASE_INK} both}}
    @keyframes uncover{{from{{transform:translateX(0)}}to{{transform:translateX(1250px)}}}}
    .frame{{animation:draw .8s {EASE_INK} forwards}}
    @keyframes draw{{to{{stroke-dashoffset:0}}}}
    .proofc{{animation:draw .7s {EASE_INK} forwards}}
    .proof{{opacity:0;animation:fade .3s ease forwards}}
    @keyframes fade{{to{{opacity:1}}}}
    .live{{animation:live 1.2s ease-in-out infinite}}
    @keyframes live{{50%{{opacity:.2}}}}
    """
    body = [f"<defs>{halftone('ht', 1.5, 8)}"]
    for i, p in enumerate(panels):
        body.append(f'<clipPath id="p{i}"><polygon points="{poly(p)}"/></clipPath>')
    body.append(f'</defs><rect width="{W}" height="{H}" fill="{PAPER}"/>')

    for i, (arc, p) in enumerate(zip(ARCS, panels)):
        x0, y0 = p[0][0] + 28 + (4 if i % 2 else 0), p[0][1]
        right = p[1][0]
        d0 = 0.3 + i * 0.55
        g = [f'<g clip-path="url(#p{i})">']
        g.append(f'<polygon points="{poly([(right - 210, y0), (right, y0), (right, y0 + 150)])}" fill="url(#ht)" opacity=".18"/>')
        # tab
        g.append(f'<rect x="{x0 - 28}" y="{y0}" width="150" height="30" fill="{INK}"/>'
                 f'<text class="muktab" x="{x0 - 14}" y="{y0 + 21}" font-size="14" fill="{PAPER}">ARC {arc["n"]} · <tspan class="mukta">{arc["hi_n"]}</tspan></text>')
        g.append(f'<text class="muktax" x="{x0}" y="{y0 + 82}" font-size="31" fill="{INK}">{arc["title"]}</text>'
                 f'<text class="rozha" x="{x0}" y="{y0 + 124}" font-size="30" fill="{SPOT}">{arc["hi"]}</text>'
                 f'<text class="mukta" x="{x0 + 190}" y="{y0 + 121}" font-size="15" fill="{INK2}">{html.escape(arc["when"])}</text>')
        ey = y0 + 162 if len(arc["eps"]) == 4 else y0 + 156
        step = 30 if len(arc["eps"]) == 4 else 27
        for k, ep in enumerate(arc["eps"]):
            g.append(f'<text class="mono" x="{x0}" y="{ey + k * step}" font-size="12" fill="{SPOT}">E{k + 1}</text>'
                     f'<text class="mukta" x="{x0 + 30}" y="{ey + k * step}" font-size="17" fill="{INK}">{html.escape(ep)}</text>')
        uy = y0 + 300
        g.append(f'<text class="muktab" x="{x0}" y="{uy}" font-size="12" fill="{INK2}" letter-spacing="1.5">UNLOCKED · <tspan class="mukta">अर्जित शक्तियाँ</tspan></text>')
        cx = x0
        for chip in arc["unlocked"]:
            w = 18 + 8.3 * len(chip)
            g.append(f'<rect x="{cx}" y="{uy + 10}" width="{w:.0f}" height="28" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>'
                     f'<text class="muktab" x="{cx + w / 2:.0f}" y="{uy + 29}" text-anchor="middle" font-size="14" fill="{INK}">{html.escape(chip)}</text>')
            cx += w + 8
        # proof stamp + editor's circle (top-right of panel)
        px, py = right - 96, y0 + 74
        g.append(f'<g class="proof" style="animation-delay:{d0 + 0.9:.2f}s"><text class="muktax" x="{px}" y="{py}" text-anchor="middle" font-size="20" fill="{SPOT}">{html.escape(arc["proof"])}</text></g>')
        g.append(editors_circle(px, py - 7, 66, 24, "proofc", round(d0 + 1.0, 2)))
        if i == 3:
            g.append(f'<circle class="live" cx="{x0 + 140}" cy="{y0 + 15}" r="5" fill="{SPOT}"/>')
        # ink slab that slides off to reveal the panel
        g.append(f'<rect class="cover rm-hide" x="{p[3][0] - 40}" y="{y0 - 10}" width="660" height="380" fill="{INK}" style="animation-delay:{d0:.2f}s"/>')
        g.append("</g>")
        g.append(f'<path class="draw frame" pathLength="1" d="{poly_path(p)}" fill="none" stroke="{INK}" stroke-width="4.5" style="animation-delay:{d0:.2f}s"/>')
        body.append("".join(g))
    return svg_doc(W, H, "Four arcs: Origin, Party, Awakening, Horizon", css, "\n".join(body))


# ---------------------------------------------------------------- Nova cascade

def nova() -> str:
    W, H = 1200, 330
    tiers = [("Instant intent", "keyword / regex", "free"),
             ("Saved automation", "learned recipes", "free"),
             ("Paraphrase match", "said differently", "free"),
             ("Free model", "picks a script", "free"),
             ("Groq + 25 tools", "web · skills", "cheap"),
             ("Claude Code", "last resort", "paid")]
    bx, bw, gap, by, bh = 36, 170, 22, 96, 104
    centers = [bx + i * (bw + gap) + bw / 2 for i in range(6)]
    T = 12  # loop seconds
    # (resolving tier, start, travel seconds)
    reqs = [(0, 0.4, 0.7), (2, 3.2, 1.3), (5, 6.2, 2.4)]

    css = [f"""
    .pk{{opacity:0}}
    .flash{{opacity:0}}
    .learn{{animation:learn {T}s {EASE_INK} infinite}}
    @keyframes learn{{0%,80%{{stroke-dashoffset:1;opacity:1}}90%,96%{{stroke-dashoffset:0;opacity:1}}100%{{stroke-dashoffset:0;opacity:0}}}}
    .learnT{{opacity:0;animation:learnT {T}s ease infinite}}
    @keyframes learnT{{0%,86%{{opacity:0}}90%,96%{{opacity:1}}100%{{opacity:0}}}}
    .meter{{animation:meter {T}s steps(1) infinite}}
    """]
    pk_svg = []
    for j, (tier, s, travel) in enumerate(reqs):
        x_end = centers[tier]
        a, b, c, e = (s / T * 100, (s + travel) / T * 100, (s + travel + 0.45) / T * 100, (s + travel + 1.1) / T * 100)
        css.append(f"""
    .pk{j}{{animation:pk{j} {T}s {EASE_SETTLE} infinite}}
    @keyframes pk{j}{{0%,{a:.2f}%{{opacity:0;transform:translate(0px,0px)}}{a + .5:.2f}%{{opacity:1;transform:translate(0px,0px)}}
      {b:.2f}%{{opacity:1;transform:translate({x_end - 18:.0f}px,0px)}}{c:.2f}%{{opacity:1;transform:translate({x_end - 18:.0f}px,96px)}}
      {e:.2f}%{{opacity:0;transform:translate({x_end - 18:.0f}px,96px)}}100%{{opacity:0;transform:translate({x_end - 18:.0f}px,96px)}}}}
    .fl{j}{{animation:fl{j} {T}s ease infinite}}
    @keyframes fl{j}{{0%,{b - .3:.2f}%{{opacity:0}}{b:.2f}%{{opacity:1}}{e + 3:.2f}%{{opacity:1}}{e + 6:.2f}%,100%{{opacity:0}}}}""")
        pk_svg.append(f'<g class="pk pk{j}"><g transform="translate(18 {by + bh / 2})">'
                      f'<line x1="-34" y1="-6" x2="-12" y2="-6" stroke="{INK}" stroke-width="2"/><line x1="-44" y1="0" x2="-12" y2="0" stroke="{INK}" stroke-width="2"/>'
                      f'<line x1="-34" y1="6" x2="-12" y2="6" stroke="{INK}" stroke-width="2"/>'
                      f'<circle r="11" fill="{SPOT}" stroke="{INK}" stroke-width="3"/></g></g>')

    boxes = []
    for i, (t, sub, cost) in enumerate(tiers):
        x = bx + i * (bw + gap)
        flash = "".join(f'<rect class="flash fl{j}" x="{x}" y="{by}" width="{bw}" height="{bh}" fill="{SPOT}" opacity="0"/>'
                        for j, (tier, _, _) in enumerate(reqs) if tier == i)
        paid = cost != "free"
        boxes.append(
            f'<rect x="{x}" y="{by}" width="{bw}" height="{bh}" fill="{PAPER}"/>'
            f'{"" if not paid else f"<rect x={chr(34)}{x}{chr(34)} y={chr(34)}{by}{chr(34)} width={chr(34)}{bw}{chr(34)} height={chr(34)}{bh}{chr(34)} fill={chr(34)}url(#ht){chr(34)} opacity={chr(34)}.18{chr(34)}/>"}'
            f'{flash}'
            f'<rect x="{x}" y="{by}" width="{bw}" height="{bh}" fill="none" stroke="{INK}" stroke-width="3.5"/>'
            f'<text class="mono" x="{x + 12}" y="{by + 24}" font-size="13" fill="{SPOT}">T{i + 1}</text>'
            f'<text class="mono" x="{x + bw - 12}" y="{by + 24}" text-anchor="end" font-size="12" fill="{INK2 if not paid else SPOT}">{cost}</text>'
            f'<text class="muktax" x="{x + 12}" y="{by + 62}" font-size="18" fill="{INK}">{html.escape(t)}</text>'
            f'<text class="mukta" x="{x + 12}" y="{by + 86}" font-size="14" fill="{INK2}">{html.escape(sub)}</text>')
        if i < 5:
            ax = x + bw
            boxes.append(f'<path d="M{ax + 3} {by + bh / 2} l{gap - 8} 0 m-6 -5 l6 5 l-6 5" fill="none" stroke="{INK}" stroke-width="2.5"/>')

    learn_d = f"M{centers[5]} {by - 4} C {centers[5]} 30, {centers[1]} 30, {centers[1]} {by - 6}"
    body = f"""
<defs>{halftone('ht', 1.5, 7)}</defs>
<rect width="{W}" height="{H}" fill="{PAPER}"/>
<rect x="2" y="2" width="{W - 4}" height="{H - 4}" fill="none" stroke="{INK}" stroke-width="4"/>
<text class="muktax" x="36" y="50" font-size="22" fill="{INK}">NOVA · how a request falls through</text>
<text class="amita" x="36" y="80" font-size="17" fill="{SPOT}">सबसे सस्ता रास्ता पहले</text>
<text class="mukta" x="1164" y="50" text-anchor="end" font-size="16" fill="{INK2}">each request is resolved by the cheapest tier that can do it</text>
<path class="learn" pathLength="1" d="{learn_d}" fill="none" stroke="{SPOT}" stroke-width="3" stroke-dasharray="1" stroke-linecap="round"/>
<g class="learnT"><rect x="560" y="22" width="180" height="26" fill="{SPOT}"/><text class="muktab" x="650" y="40" text-anchor="middle" font-size="14" fill="{PAPER}">learns a recipe · सीख लिया</text></g>
{''.join(boxes)}
<line x1="36" y1="{by + bh + 92}" x2="1164" y2="{by + bh + 92}" stroke="{INK}" stroke-width="3" stroke-dasharray="10 8"/>
<rect x="36" y="{by + bh + 76}" width="156" height="32" fill="{INK}"/>
<text class="muktab" x="114" y="{by + bh + 98}" text-anchor="middle" font-size="15" fill="{PAPER}">DONE · हो गया</text>
{''.join(pk_svg)}
"""
    return svg_doc(W, H, "Nova request cascade: six tiers, cheapest first", "".join(css), body)


# ---------------------------------------------------------------- footer

def footer() -> str:
    W, H = 1200, 230
    css = f"""
    .name{{fill:transparent;stroke:{INK};stroke-width:1.3;stroke-dasharray:1600;stroke-dashoffset:1600;
      animation:ink 2.2s cubic-bezier(.35,.1,.25,1) .2s forwards,inkFill .6s ease 1.6s forwards}}
    @keyframes ink{{to{{stroke-dashoffset:0}}}}
    @keyframes inkFill{{to{{fill:{INK};stroke-width:.3}}}}
    .rise{{opacity:0;animation:rise .7s {EASE_SETTLE} forwards}}
    @keyframes rise{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
    .flA{{animation:flick .3s steps(1) infinite}}
    @keyframes flick{{50%{{opacity:0}}}}
    .dots{{animation:dots 1.6s steps(4) infinite}}
    @keyframes dots{{from{{stroke-dashoffset:0}}to{{stroke-dashoffset:-40}}}}
    """
    fl = focus_lines(600, 112, 90, 260, 720, 0.02)
    body = f"""
<defs><clipPath id="c"><rect x="4" y="4" width="{W - 8}" height="{H - 8}"/></clipPath></defs>
<rect width="{W}" height="{H}" fill="{PAPER}"/>
<g clip-path="url(#c)"><g fill="{INK}" opacity=".85" class="flA">{fl}</g>
<ellipse cx="600" cy="112" rx="400" ry="96" fill="{PAPER}"/></g>
<rect x="2" y="2" width="{W - 4}" height="{H - 4}" fill="none" stroke="{INK}" stroke-width="4"/>
<text class="rozha name" x="600" y="122" text-anchor="middle" font-size="76">जारी रहेगा…</text>
<text class="muktax rise" x="600" y="160" text-anchor="middle" font-size="18" fill="{INK}" letter-spacing="8" style="animation-delay:1.8s">TO BE CONTINUED</text>
<text class="amita rise" x="600" y="194" text-anchor="middle" font-size="17" fill="{SPOT}" style="animation-delay:2.1s">चाल आपकी · your move · कानपुर से स्नेह सहित</text>
"""
    return svg_doc(W, H, "To be continued", css, body)


# ---------------------------------------------------------------- main

HEADERS = {
    "prologue": ("Prologue", "प्रस्तावना", "gamer → builder → founder", "p. 02"),
    "work": ("The work", "कारनामे", "main quests, ordered by impact", "p. 03"),
    "arcs": ("Arcs", "पर्व", "four arcs out of Kanpur", "p. 04"),
    "skills": ("Skill tree", "कौशल वृक्ष", "inked by how often each skill ships", "p. 05"),
    "feats": ("Feats", "उपलब्धियाँ", "hackathons, finals and the commit log", "p. 06"),
    "stats": ("Numbers", "आँकड़े", "the contribution graph keeps score", "p. 07"),
    "contact": ("Your move", "संपर्क", "the next arc starts with a message", "p. 08"),
}


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    out = {"cover.svg": cover(), "arcs.svg": arcs(), "nova.svg": nova(), "footer.svg": footer()}
    for key, args in HEADERS.items():
        out[f"h-{key}.svg"] = header(*args)
    for name, svg in out.items():
        (ASSETS / name).write_text(svg, encoding="utf-8")
        print(f"{name:16s} {len(svg) / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
