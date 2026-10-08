"""Builds the animated manga-ink SVGs used by the profile README.

Styling mirrors https://aakshantkumar.vercel.app : paper / ink / spot pink,
Rozha One + Amita + Mukta, ink-stroke reveals and "editor's circle" proofs.

Display Devanagari (Rozha One) is shaped with HarfBuzz and outlined to paths;
body fonts are subset per SVG and embedded as base64 WOFF so they render
inside GitHub's <img> sandbox (which can't fetch web fonts).

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


_SHAPERS: dict[str, tuple] = {}


def shaped_path(alias: str, text: str, x: float, y: float, size: float, anchor: str = "start") -> str:
    """Shapes text with HarfBuzz on the *full* font and returns SVG outline data.

    Used for display Devanagari: conjuncts and the joined shirorekha come out
    exactly as the type designer intended, independent of the viewer's
    browser or of what font subsetting keeps.
    """
    import uharfbuzz as hb
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen

    if alias not in _SHAPERS:
        p = _font_path(alias)
        blob = hb.Blob.from_file_path(str(p))
        _SHAPERS[alias] = (hb.Font(hb.Face(blob)), TTFont(p))
    hb_font, tt = _SHAPERS[alias]
    upem = tt["head"].unitsPerEm
    gs = tt.getGlyphSet()
    order = tt.getGlyphOrder()

    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)

    s = size / upem
    width = sum(p.x_advance for p in buf.glyph_positions) * s
    x0 = x - (width if anchor == "end" else width / 2 if anchor == "middle" else 0)

    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    cx = cy = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        gx = x0 + (cx + pos.x_offset) * s
        gy = y - (cy + pos.y_offset) * s
        gs[order[info.codepoint]].draw(TransformPen(pen, (s, 0, 0, -s, gx, gy)))
        cx += pos.x_advance
        cy += pos.y_advance
    return pen.getCommands()


# classes whose <text> is drawn as shaped paths: Devanagari display faces, plus
# out* aliases for Latin titles that need an ink-stroke draw (pathLength=1)
_OUTLINED = {"rozha": "Rozha", "amita": "Amita", "outx": "MuktaX", "outb": "MuktaB", "outr": "Mukta"}
_DISPLAY_TEXT = re.compile(r'<text class="(rozha|amita|outx|outb|outr)( [^"]*)?"([^>]*)>([^<]*)</text>')


def measure(alias: str, text: str, size: float) -> float:
    """Advance width of text in px, shaped exactly as the browser will shape it."""
    import uharfbuzz as hb
    shaped_path(alias, " ", 0, 0, size)  # warms the shaper cache
    hb_font, tt = _SHAPERS[alias]
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)
    return sum(p.x_advance for p in buf.glyph_positions) * size / tt["head"].unitsPerEm


def _outline_display(body: str) -> str:
    """Replaces every <text class="rozha|amita …"> with a shaped <path>, keeping its other attributes."""
    def repl(m: re.Match) -> str:
        alias = _OUTLINED[m.group(1)]
        classes, attrs, text = (m.group(2) or "").strip(), m.group(3), html.unescape(m.group(4))
        get = lambda k, d=None: (re.search(rf'\b{k}="([^"]*)"', attrs) or [None, d])[1]
        d = shaped_path(alias, text, float(get("x", 0)), float(get("y", 0)),
                        float(get("font-size", 16)), get("text-anchor", "start"))
        rest = re.sub(r'\s(x|y|font-size|text-anchor)="[^"]*"', "", attrs)
        cls = f' class="{classes}"' if classes else ""
        # pathLength lets the ink-draw animation use a 0..1 dash regardless of outline length
        return f'<path{cls}{rest} pathLength="1" d="{d}"><title>{html.escape(text)}</title></path>'
    return _DISPLAY_TEXT.sub(repl, body)


def svg_doc(w: int, h: int, label: str, css: str, body: str) -> str:
    """Wraps body, embedding a subset of each font family referenced by a class."""
    body = _outline_display(body)
    texts =" ".join(html.unescape(t) for t in re.findall(r">([^<>]+)<", body))
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
    .name{{fill:transparent;stroke:{INK};stroke-width:1.4;stroke-dasharray:1;stroke-dashoffset:1;
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
    .name{{fill:transparent;stroke:{INK};stroke-width:1.3;stroke-dasharray:1;stroke-dashoffset:1;
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


# ---------------------------------------------------------------- animated text blocks

TEXT_CSS = f"""
    .w{{opacity:0;animation:wIn .55s {EASE_SETTLE} forwards}}
    @keyframes wIn{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
    .hl{{transform-box:fill-box;transform-origin:0 50%;transform:scaleX(0);animation:grow .5s {EASE_INK} forwards}}
    @keyframes grow{{to{{transform:scaleX(1)}}}}
    .wipe{{transform-box:fill-box;transform-origin:0 50%;transform:scaleX(0);animation:grow .7s {EASE_INK} forwards}}
    .rise{{opacity:0;animation:rise .7s {EASE_SETTLE} forwards}}
    @keyframes rise{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
    .pop{{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.34,1.8,.5,1) forwards}}
    @keyframes pop{{0%{{opacity:0;transform:scale(2) rotate(-14deg)}}100%{{opacity:1;transform:scale(1) rotate(-3deg)}}}}
    .ink{{fill:transparent;stroke:{INK};stroke-width:1.2;stroke-dasharray:1;stroke-dashoffset:1;
      animation:inkDraw 1.5s cubic-bezier(.35,.1,.25,1) forwards,inkFill .5s ease forwards}}
    @keyframes inkDraw{{to{{stroke-dashoffset:0}}}}
    @keyframes inkFill{{to{{fill:{INK};stroke-width:.2}}}}
    .blink{{animation:blink 1s steps(1) infinite}}
    @keyframes blink{{50%{{opacity:0}}}}
    .pulse{{transform-box:fill-box;transform-origin:center;animation:pulse 1.6s ease-in-out infinite}}
    @keyframes pulse{{50%{{transform:scale(1.6);opacity:.35}}}}
"""


def flow(text: str, x: float, y: float, width: float, size: float, lh: float, t0: float,
         step: float = 0.03, color: str = INK) -> tuple[str, float, float]:
    """Word-by-word rising paragraph; **phrases** go bold and get a pink highlighter sweep.

    Returns (svg, baseline of last line, time the last word starts).
    """
    tokens = [(w, i % 2 == 1) for i, part in enumerate(text.split("**")) for w in part.split()]
    space = measure("Mukta", " ", size)
    lines, cur, cx = [], [], 0.0
    for word, bold in tokens:
        ww = measure("MuktaB" if bold else "Mukta", word, size)
        if cur and cx + ww > width:
            lines.append(cur)
            cur, cx = [], 0.0
        cur.append((word, bold, cx, ww))
        cx += ww + space
    lines.append(cur)

    words, marks, t = [], [], t0
    for li, line in enumerate(lines):
        yy = y + li * lh
        run = None
        for word, bold, wx, ww in line:
            words.append(f'<text class="{"muktab" if bold else "mukta"} w rm-show" x="{x + wx:.1f}" y="{yy:.1f}" '
                         f'font-size="{size}" fill="{color}" style="animation-delay:{t:.2f}s">{html.escape(word)}</text>')
            if bold:
                if run is None:
                    run = [wx, 0.0, yy, t]
                run[1] = wx + ww
            elif run is not None:
                marks.append(run)
                run = None
            t += step
        if run is not None:
            marks.append(run)
    hl = "".join(
        f'<rect class="hl rm-show" x="{x + a - 4:.1f}" y="{yy - size * 0.74:.1f}" width="{b - a + 8:.1f}" height="{size * 0.98:.1f}" '
        f'fill="{SPOT}" opacity=".26" style="animation-delay:{ts + 0.35:.2f}s"/>'
        for a, b, yy, ts in marks)
    return hl + "".join(words), y + (len(lines) - 1) * lh, t


def prologue() -> str:
    W = 1200
    p1 = ("I came up as a gamer, and somewhere along the way the centre of gravity moved from "
          "**playing to building.** Now I'm a third-year **B.Tech CSE (AI)** student at CSJM University, Kanpur, "
          "**Co-founder & VP Tech at Kaiketsu Tech,** and founder of the hackathon squad **Void Walkers.**")
    p2 = ("I work across the whole stack: I fine-tune the model, put an API around it, and **ship the product** "
          "in front of real users. I'm as happy arguing about backend routing as about a hero animation, "
          "and I'll pick **premium craft over templates** every time.")
    a, y1, t1 = flow(p1, 64, 76, 1080, 22, 36, 0.3)
    b, y2, t2 = flow(p2, 64, y1 + 56, 1080, 22, 36, t1 + 0.25)
    hy = y2 + 62
    H = int(hy + 34)
    hi = "खिलाड़ी से निर्माता, निर्माता से संस्थापक।"
    hw = measure("Amita", hi, 26)
    body = f"""
<defs>{halftone('ht', 1.5, 8)}<clipPath id="hiw"><rect class="wipe" x="60" y="{hy - 36}" width="{hw + 12:.0f}" height="52" style="animation-delay:{t2 + 0.5:.2f}s"/></clipPath></defs>
<rect width="{W}" height="{H}" fill="{PAPER}"/>
<polygon points="{poly([(W - 260, 0), (W, 0), (W, 200)])}" fill="url(#ht)" opacity=".16"/>
<rect x="2" y="2" width="{W - 4}" height="{H - 4}" fill="none" stroke="{INK}" stroke-width="4"/>
<rect x="24" y="0" width="156" height="30" fill="{INK}"/>
<text class="outb" x="40" y="21" font-size="14" fill="{PAPER}">NARRATION · कथा</text>
{a}{b}
<g clip-path="url(#hiw)"><text class="amita" x="66" y="{hy}" font-size="26" fill="{SPOT}">{hi}</text></g>
<path class="draw rm-show" pathLength="1" d="M66 {hy + 12} C{66 + hw * .3:.0f} {hy + 6} {66 + hw * .7:.0f} {hy + 18} {66 + hw:.0f} {hy + 10}"
  fill="none" stroke="{INK}" stroke-width="3" stroke-linecap="round" style="animation:grow 0s,inkDraw .6s {EASE_INK} {t2 + 1.1:.2f}s forwards"/>
"""
    return svg_doc(W, H, "Prologue: " + re.sub(r"\*\*", "", p1 + " " + p2) + " " + hi, TEXT_CSS, body)


def now_panel() -> str:
    W, H = 1200, 262
    cols = [
        ("RESEARCH · शोध", 24, ["Affective computing & emotion ambiguity", "Multi-agent and voice-first systems",
                                "Lightweight multimodal fusion", "TinyML and edge inference"], False),
        ("RIGHT NOW · अभी", 612, ["Nova: a local voice OS for Windows 11", "Drishtikon: VLM for satellite imagery",
                                  "Drafting the AirGated paper for arXiv", "Exoplanet hunts on TESS light curves"], True),
    ]
    out, clips = [f'<rect width="{W}" height="{H}" fill="{PAPER}"/>'], []
    for ci, (label, x0, items, live) in enumerate(cols):
        bw = 564
        out.append(f'<rect x="{x0}" y="18" width="{bw}" height="{H - 36}" fill="{PAPER}" stroke="{INK}" stroke-width="4"/>')
        lw = measure("MuktaB", label, 15) + 30
        out.append(f'<rect x="{x0}" y="18" width="{lw:.0f}" height="32" fill="{INK}"/>'
                   f'<text class="outb" x="{x0 + 15}" y="40" font-size="15" fill="{PAPER}">{label}</text>')
        if live:
            out.append(f'<g class="rise" style="animation-delay:.2s"><circle class="pulse" cx="{x0 + bw - 70}" cy="34" r="6" fill="{SPOT}"/>'
                       f'<text class="mono blink" x="{x0 + bw - 56}" y="39" font-size="13" fill="{SPOT}">LIVE</text></g>')
        for k, item in enumerate(items):
            y = 92 + k * 44
            d = 0.35 + ci * 0.25 + k * 0.32
            iw = measure("Mukta", item, 20)
            cid = f"r{ci}{k}"
            clips.append(f'<clipPath id="{cid}"><rect class="wipe" x="{x0 + 46}" y="{y - 24}" width="{iw + 8:.0f}" height="34" style="animation-delay:{d + .12:.2f}s"/></clipPath>')
            # an ink block runs ahead of the reveal, like a brush laying the line down
            out.append(f'<rect class="pop" x="{x0 + 22}" y="{y - 14}" width="12" height="12" fill="{SPOT if live else INK}" style="animation-delay:{d:.2f}s"/>'
                       f'<g clip-path="url(#{cid})"><text class="mukta" x="{x0 + 50}" y="{y}" font-size="20" fill="{INK}">{html.escape(item)}</text></g>'
                       f'<rect x="{x0 + 46}" y="{y - 22}" width="10" height="30" fill="{INK}" opacity="0" '
                       f'style="animation:runner .7s {EASE_INK} {d + .12:.2f}s forwards;--to:{iw:.0f}px"/>')
    css = TEXT_CSS + """
    @keyframes runner{0%{opacity:1;transform:translateX(0)}90%{opacity:1;transform:translateX(var(--to))}100%{opacity:0;transform:translateX(var(--to))}}
    """
    body = f"<defs>{''.join(clips)}</defs>" + "".join(out)
    label = "Research: " + "; ".join(cols[0][2]) + ". Right now: " + "; ".join(cols[1][2]) + "."
    return svg_doc(W, H, label, css, body)


TITLES = {
    "nova": ("Nova · AssisstantOS", "658 TESTS · BUILT IN 15 DAYS", "a voice OS that gets cheaper"),
    "vedavoice": ("VedaVoice", "FINALIST · MIND INSTALLERS 4.0", "a.k.a. Parchi"),
    "airgated": ("AirGated", "PAPER IN PREP · arXiv", "offline identity"),
    "void": ("Void / AmbiSense", "ENTERED · OPENCV AI 2026", "edge emotion"),
    "civicpulse": ("CivicPulse", "BUILD WITH BHARAT 2.0", "jurisdiction routing"),
    "exoplanet": ("Exoplanet Hunt", "ACTIVE · TESS DATA", "light curves"),
    "student": ("CSJMU Assistant", "MULTI-TIER RAG", "for my university"),
    "robo": ("Robo Rumble 3.0", "113 / 292 COMMITS", "most of anyone"),
    "riseup": ("Rise UP School", "IN PRODUCTION", "81 endpoints"),
}


def title_card(title: str, stamp: str, aside: str) -> str:
    """Compact (620px) so it stays legible when GitHub squeezes it into a table cell."""
    W, H = 620, 128
    size = 46
    tw = measure("MuktaX", title, size)
    sw = measure("MuktaB", stamp, 17) + 28
    body = f"""
<defs>{halftone('ht', 1.4, 7)}</defs>
<rect width="{W}" height="{H}" fill="{PAPER}"/>
<polygon points="{poly([(W - 150, 0), (W, 0), (W, 110)])}" fill="url(#ht)" opacity=".2"/>
<g class="pop" style="animation-delay:.05s"><rect x="14" y="30" width="20" height="20" fill="{SPOT}" stroke="{INK}" stroke-width="3" transform="rotate(45 24 40)"/></g>
<text class="outx ink" x="48" y="56" font-size="{size}" style="animation-delay:.15s,1.2s">{html.escape(title)}</text>
<path class="draw rm-show" pathLength="1" d="M48 70 C{48 + tw * .35:.0f} 64 {48 + tw * .7:.0f} 76 {48 + tw:.0f} 68" fill="none" stroke="{SPOT}" stroke-width="4"
  stroke-linecap="round" style="animation:inkDraw .6s {EASE_INK} 1.3s forwards"/>
<g class="pop" style="animation-delay:1.6s">
  <rect x="50" y="84" width="{sw:.0f}" height="32" fill="{SPOT}" stroke="{INK}" stroke-width="2.5"/>
  <text class="muktab" x="{50 + sw / 2:.0f}" y="106" text-anchor="middle" font-size="17" fill="{PAPER}">{html.escape(stamp)}</text>
</g>
<text class="amita rise" x="{50 + sw + 18:.0f}" y="108" font-size="21" fill="{INK2}" style="animation-delay:1.9s">{html.escape(aside)}</text>
<rect x="1.5" y="1.5" width="{W - 3}" height="{H - 3}" fill="none" stroke="{INK}" stroke-width="3"/>
"""
    return svg_doc(W, H, f"{title}: {stamp}", TEXT_CSS, body)


def tickers() -> str:
    W, H = 1200, 172
    en = ["FINALIST · MIND INSTALLERS 4.0", "FINALIST · HACKSHODH", "113 / 292 COMMITS · ROBO RUMBLE 3.0",
          "SIH 2026 · TEAM VAYU", "BUILD WITH BHARAT 2.0", "OPENCV AI COMPETITION 2026",
          "GOOGLE GENAI APAC 2026", "VP TECH · KAIKETSU TECH"]
    hi = ["फ़ाइनलिस्ट", "हैकाथॉन", "कमिट", "दल", "शोध", "निर्माण", "जीत", "जारी"]
    en_s = "   •   ".join(en) + "   •   "
    hi_s = "  ✦  ".join(hi) + "  ✦  "
    le = measure("MuktaX", en_s, 24)
    lh_ = measure("Rozha", hi_s.replace("✦", "•"), 30)
    en_copies = "".join(f'<text class="muktax" x="{i * le:.1f}" y="0" font-size="24" fill="{PAPER}">{html.escape(en_s)}</text>' for i in range(3))
    hi_copies = "".join(f'<text class="rozha" x="{i * lh_:.1f}" y="0" font-size="30" fill="{INK}">{hi_s.replace("✦", "•")}</text>' for i in range(4))
    css = f"""
    .tA{{animation:tA 38s linear infinite}} @keyframes tA{{to{{transform:translateX(-{le:.1f}px)}}}}
    .tB{{animation:tB 30s linear infinite}} @keyframes tB{{from{{transform:translateX(-{lh_:.1f}px)}}to{{transform:translateX(0)}}}}
    """
    body = f"""
<rect width="{W}" height="{H}" fill="{PAPER}"/>
<g transform="rotate(-0.4 600 124)">
  <rect x="-40" y="100" width="{W + 80}" height="48" fill="{SPOT}" stroke="{INK}" stroke-width="3"/>
  <g transform="translate(0 135)"><g class="tB">{hi_copies}</g></g>
</g>
<g transform="rotate(-1.4 600 50)">
  <rect x="-40" y="24" width="{W + 80}" height="52" fill="{INK}"/>
  <g transform="translate(0 59)"><g class="tA">{en_copies}</g></g>
</g>
<rect x="2" y="2" width="{W - 4}" height="{H - 4}" fill="none" stroke="{INK}" stroke-width="4"/>
"""
    return svg_doc(W, H, "Feats: " + "; ".join(en), css, body)


def contact_bubble() -> str:
    W, H = 1200, 214
    line = "The next arc starts with a message."
    size = 34
    tw = measure("MuktaX", line, size)
    x0 = (W - tw) / 2
    # one keyframe per character, so the caret lands on real glyph boundaries
    n, dur, start = len(line), 2.2, 0.5
    kf_clip, kf_caret = [], []
    for i in range(n + 1):
        pct = i / n * 100
        w = measure("MuktaX", line[:i], size) if i else 0.0
        kf_clip.append(f"{pct:.2f}%{{transform:scaleX({w / tw:.4f})}}")
        kf_caret.append(f"{pct:.2f}%{{transform:translateX({w:.1f}px)}}")
    css = TEXT_CSS + f"""
    .type{{transform-box:fill-box;transform-origin:0 50%;transform:scaleX(0);animation:type {dur}s steps(1,end) {start}s forwards}}
    @keyframes type{{{''.join(kf_clip)}}}
    .caret{{animation:caret {dur}s steps(1,end) {start}s forwards}}
    @keyframes caret{{{''.join(kf_caret)}}}
    """
    sub = "Internships · research collaborations · hackathon teams · a website for your business"
    t_end = start + dur
    bubble = (f"M140 30 Q140 18 156 18 L1044 18 Q1060 18 1060 30 L1060 148 Q1060 160 1044 160 "
              f"L640 160 L596 196 L604 160 L156 160 Q140 160 140 148 Z")
    body = f"""
<defs><clipPath id="tc"><rect class="type" x="{x0 - 2:.1f}" y="40" width="{tw + 6:.1f}" height="60"/></clipPath></defs>
<g class="pop" style="animation-delay:.05s;animation-name:bub">
  <path d="{bubble}" fill="{PAPER}" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>
</g>
<g clip-path="url(#tc)"><text class="muktax" x="{x0:.1f}" y="82" font-size="{size}" fill="{INK}">{html.escape(line)}</text></g>
<g class="caret"><rect class="blink" x="{x0 + 2:.1f}" y="52" width="4" height="38" fill="{SPOT}"/></g>
<text class="amita rise" x="600" y="122" text-anchor="middle" font-size="24" fill="{SPOT}" style="animation-delay:{t_end + .1:.2f}s">एक ईमेल काफ़ी है।</text>
<text class="mukta rise" x="600" y="148" text-anchor="middle" font-size="16" fill="{INK2}" style="animation-delay:{t_end + .35:.2f}s">{html.escape(sub)}</text>
"""
    css += "@keyframes bub{0%{opacity:0;transform:scale(.7)}100%{opacity:1;transform:none}}"
    return svg_doc(W, H, f"{line} एक ईमेल काफ़ी है। {sub}", css, body)


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
    out = {"cover.svg": cover(), "arcs.svg": arcs(), "nova.svg": nova(), "footer.svg": footer(),
           "prologue.svg": prologue(), "now.svg": now_panel(), "feats-ticker.svg": tickers(),
           "contact.svg": contact_bubble()}
    for key, args in HEADERS.items():
        out[f"h-{key}.svg"] = header(*args)
    for key, args in TITLES.items():
        out[f"t-{key}.svg"] = title_card(*args)
    for name, svg in out.items():
        (ASSETS / name).write_text(svg, encoding="utf-8")
        print(f"{name:16s} {len(svg) / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
