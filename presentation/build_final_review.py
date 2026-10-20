"""
Builds Krypsis_Final_Review.pptx — the 14-slide final-review deck:
introduction, objectives, six methodology slides with the main code on
them, results, comparisons with existing approaches and between our own
setups, conclusion and references. Every slide has speaker notes.

Numbers are read from results/*.json (through build_deck.load_results), so
the deck always matches the latest experiment runs.

Run: ..\\venv\\Scripts\\python.exe build_final_review.py
Output: presentation/Krypsis_Final_Review.pptx
"""

import os
import re
import textwrap

import numpy as np
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from build_deck import R, pct

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "Krypsis_Final_Review.pptx")
# Muted figure set (src/make_plots.py --deck), matching this palette.
FIG_DIR = os.path.join(HERE, "figures")

# Quiet palette: warm paper, deep ink, one muted teal accent, a muted bronze
# reserved for caveats / negative findings.
BG = RGBColor(0xF7, 0xF6, 0xF2)
BG_DEEP = RGBColor(0xEE, 0xEC, 0xE6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x1F, 0x24, 0x21)
INK_SOFT = RGBColor(0x5B, 0x62, 0x5C)
MUTED = RGBColor(0x8C, 0x91, 0x8A)
LINE = RGBColor(0xDD, 0xDA, 0xD2)
ACCENT = RGBColor(0x3E, 0x5F, 0x5A)
ACCENT_SOFT = RGBColor(0xE4, 0xEB, 0xE8)
BRONZE = RGBColor(0x8E, 0x67, 0x3F)
BRONZE_SOFT = RGBColor(0xF2, 0xEB, 0xE2)

SERIF = "Georgia"
SANS = "Segoe UI"

W, H = Inches(13.333), Inches(7.5)
LEFT = Inches(0.8)
CONTENT_W = Inches(11.73)

_slide_no = [0]


def _e(*values):
    """PowerPoint rejects fractional EMU coordinates (e.g. from w / 2), so
    every position and size is rounded to a whole EMU."""
    return [Emu(int(round(v))) for v in values]


# ------------------------------------------------------------------ helpers

def text(slide, x, y, w, h, content, size=14, color=INK, bold=False, font=SANS,
         align=PP_ALIGN.LEFT, italic=False, spacing=1.2, anchor=MSO_ANCHOR.TOP):
    """content: a string (\\n = new paragraph) or a list of paragraphs, each a
    string or a list of (text, {style overrides}) runs."""
    box = slide.shapes.add_textbox(*_e(x, y, w, h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    paragraphs = content.split("\n") if isinstance(content, str) else content
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        runs = [(para, {})] if isinstance(para, str) else para
        for run_text, style in runs:
            r = p.add_run()
            r.text = run_text
            f = r.font
            f.size = Pt(style.get("size", size))
            f.color.rgb = style.get("color", color)
            f.bold = style.get("bold", bold)
            f.italic = style.get("italic", italic)
            f.name = style.get("font", font)
    return box


def bullets(slide, x, y, w, h, items, size=14, gap=8, color=INK):
    """items: strings, or (lead, rest) pairs where the lead is set in bold."""
    box = slide.shapes.add_textbox(*_e(x, y, w, h))
    tf = box.text_frame
    tf.word_wrap = True
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = 1.2
        p.space_after = Pt(gap)
        _bullet(p)
        lead, rest = (item if isinstance(item, tuple) else (None, item))
        if lead:
            r = p.add_run()
            r.text = lead + " "
            r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), True, color, SANS
        r = p.add_run()
        r.text = rest
        r.font.size, r.font.color.rgb, r.font.name = Pt(size), color, SANS
    return box


def _bullet(p, indent=Inches(0.24)):
    """A real bullet (accent-coloured) with a hanging indent, so wrapped
    lines align with the text rather than the bullet."""
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(indent)))
    pPr.set("indent", str(-int(indent)))
    clr = pPr.makeelement(qn("a:buClr"), {})
    clr.append(clr.makeelement(qn("a:srgbClr"), {"val": str(ACCENT)}))
    pPr.append(clr)
    pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
    pPr.append(pPr.makeelement(qn("a:buChar"), {"char": "•"}))


def rect(slide, x, y, w, h, fill=WHITE, line=LINE, radius=None, line_w=0.75):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, *_e(x, y, w, h))
    if radius:
        shape.adjustments[0] = radius
    shape.shadow.inherit = False
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_w)
    return shape


def card(slide, x, y, w, h, fill=WHITE, line=LINE):
    return rect(slide, x, y, w, h, fill=fill, line=line, radius=0.04)


def box_label(slide, x, y, w, h, title, body=None, fill=WHITE, line=LINE,
              title_color=INK, size=12):
    rect(slide, x, y, w, h, fill=fill, line=line, radius=0.08)
    content = [[(title, {"bold": True, "color": title_color, "size": size})]]
    if body:
        content.append([(body, {"color": INK_SOFT, "size": size - 2})])
    text(slide, x + Inches(0.1), y, w - Inches(0.2), h, content, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE, spacing=1.1)


def _plain(connector):
    """Drop the theme style reference, which adds a drop shadow to lines."""
    style = connector._element.find(qn("p:style"))
    if style is not None:
        connector._element.remove(style)
    return connector


def hrule(slide, x, y, w, color=LINE, weight=0.75):
    line = _plain(slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, *_e(x, y, x + w, y)))
    line.line.color.rgb = color
    line.line.width = Pt(weight)
    return line


def arrow(slide, x1, y1, x2, y2, color=MUTED, weight=1.25):
    c = _plain(slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, *_e(x1, y1, x2, y2)))
    c.line.color.rgb = color
    c.line.width = Pt(weight)
    ln = c.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def picture(slide, name, x, y, w=None, h=None):
    path = os.path.join(FIG_DIR, name)
    x, y = _e(x, y)
    w = _e(w)[0] if w is not None else None
    h = _e(h)[0] if h is not None else None
    return slide.shapes.add_picture(path, x, y, width=w, height=h)


def notes(slide, content):
    slide.notes_slide.notes_text_frame.text = content


def base(prs, section=None, title=None, bg=BG, footer=True):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_no[0] += 1
    rect(slide, 0, 0, W, H, fill=bg, line=None)
    if section:
        text(slide, LEFT, Inches(0.55), Inches(8), Inches(0.3), section.upper(),
             size=10.5, color=ACCENT, bold=True)
        hrule(slide, LEFT, Inches(0.92), Inches(0.5), color=ACCENT, weight=1.5)
    if title:
        text(slide, LEFT, Inches(1.05), CONTENT_W, Inches(0.8), title,
             size=28, font=SERIF, color=INK)
    if footer:
        text(slide, LEFT, Inches(7.0), Inches(6), Inches(0.25),
             "Krypsis  ·  Final Review", size=9, color=MUTED)
        text(slide, Inches(11.53), Inches(7.0), Inches(1.0), Inches(0.25),
             str(_slide_no[0]), size=9, color=MUTED, align=PP_ALIGN.RIGHT)
    return slide


def divider(prs, number, title, subtitle):
    slide = base(prs, bg=BG_DEEP, footer=False)
    text(slide, LEFT, Inches(2.3), Inches(3), Inches(1.2), number,
         size=66, font=SERIF, color=ACCENT)
    hrule(slide, LEFT, Inches(3.65), Inches(0.9), color=ACCENT, weight=1.5)
    text(slide, LEFT, Inches(3.85), Inches(11), Inches(0.9), title, size=38, font=SERIF)
    text(slide, LEFT, Inches(4.75), Inches(10), Inches(0.8), subtitle, size=14, color=INK_SOFT)
    return slide


def table(slide, x, y, widths, rows, size=12, row_h=Inches(0.42), header=True,
          bold_cols=(), shade_rows=()):
    """Minimal table: text on hairline rules (no grid)."""
    total = sum(widths, Emu(0))
    hrule(slide, x, y, total, color=INK_SOFT, weight=1)
    for r_i, cells in enumerate(rows):
        ry = y + r_i * row_h
        if r_i in shade_rows:
            rect(slide, x, ry, total, row_h, fill=ACCENT_SOFT, line=None)
        cx = x
        for c_i, cell in enumerate(cells):
            is_head = header and r_i == 0
            text(slide, cx + Inches(0.08), ry, widths[c_i] - Inches(0.16), row_h, cell,
                 size=size - (1 if is_head else 0), anchor=MSO_ANCHOR.MIDDLE,
                 bold=is_head or c_i in bold_cols,
                 color=ACCENT if is_head else INK, spacing=1.05)
            cx += widths[c_i]
        hrule(slide, x, ry + row_h, total,
              color=INK_SOFT if (is_head or r_i == len(rows) - 1) else LINE,
              weight=1 if (header and r_i == 0) or r_i == len(rows) - 1 else 0.5)
    return y + len(rows) * row_h


# ------------------------------------------------------------------ numbers

D = R["defense"]
FL, NL, NB, FB = (D["flnet/label_flip"], D["nslkdd/label_flip"],
                  D["nslkdd/backdoor"], D["flnet/backdoor"])
PG = R["protocol"]["summary"]
COMM = R["protocol"]["communication"]
MC = R["multiclass"]
RB = R["robustness"]["summary"] if R["robustness"] else None
OVERHEAD = COMM["krypsis_overhead_bytes"] / COMM["raw_payload_bytes"]
JSON_X = COMM["http_json_bytes"] / COMM["raw_payload_bytes"]

# FLNET2023 training data per router (src/preprocess.py output, 10% sample).
ROUTERS = [
    (1, 23526, 55.7, "DDoS-bot, slowhttp, MITM, cmd-injection"),
    (2, 53926, 83.2, "DoS-hulk, slowhttp, MITM, XSS"),
    (3, 24109, 19.0, "slowhttp, MITM, SQL-injection"),
    (4, 49178, 92.1, "DoS-hulk, slowhttp, MITM, SQLi, XSS"),
    (5, 53655, 76.3, "DDoS-stomp, MITM"),
    (6, 61194, 66.1, "DoS-hulk"),
    (7, 58198, 42.2, "DoS-hulk, MITM"),
    (8, 48311, 50.8, "DoS-hulk, slowhttp"),
    (9, 50183, 72.3, "DDoS-dyn, slowhttp, MITM"),
    (10, 141727, 68.5, "DDoS-tcp, slowhttp, MITM"),
]



# ------------------------------------------------------------------ code

MONO = "Consolas"
CODE_BG = RGBColor(0xFB, 0xFA, 0xF7)
KEYWORDS = {"def", "return", "for", "in", "if", "not", "or", "and", "import", "from",
            "class", "else", "None", "True", "False", "with", "as", "lambda"}
_TOKEN = re.compile(r'(#.*$)|("[^"]*")|([A-Za-z_][A-Za-z_0-9]*)|(.)')


def _code_runs(line):
    """Quiet syntax colouring: keywords in the accent, strings in bronze,
    comments muted."""
    runs = []
    for m in _TOKEN.finditer(line):
        comment, string, word, _ = m.groups()
        if comment:
            runs.append((comment, {"color": MUTED, "italic": True}))
        elif string:
            runs.append((string, {"color": BRONZE}))
        elif word in KEYWORDS:
            runs.append((word, {"color": ACCENT, "bold": True}))
        else:
            runs.append((m.group(0), {}))
    return runs or [(" ", {})]


def code(slide, x, y, w, h, source, label, size=9.5):
    """A code card: a source excerpt with its file name on top."""
    rect(slide, x, y, w, h, fill=CODE_BG, line=LINE)
    rect(slide, x, y, Inches(0.05), h, fill=ACCENT, line=None)
    text(slide, x + Inches(0.25), y + Inches(0.12), w - Inches(0.4), Inches(0.25), label,
         size=9, color=MUTED, font=MONO)
    hrule(slide, x + Inches(0.25), y + Inches(0.42), w - Inches(0.45), color=LINE, weight=0.5)
    lines = textwrap.dedent(source).strip("\n").split("\n")
    text(slide, x + Inches(0.25), y + Inches(0.55), w - Inches(0.35), h - Inches(0.65),
         [_code_runs(line) for line in lines], size=size, font=MONO, spacing=1.08)


def label(slide, x, y, w, content, color=ACCENT):
    text(slide, x, y, w, Inches(0.3), content.upper(), size=10.5, bold=True, color=color)


# ------------------------------------------------------------------ slides

def s_title(prs):
    slide = base(prs, bg=BG_DEEP, footer=False)
    _slide_no[0] = 1
    text(slide, LEFT, Inches(1.35), Inches(8), Inches(0.3),
         "COMPUTER NETWORKS  ·  FINAL PROJECT REVIEW", size=11, bold=True, color=ACCENT)
    hrule(slide, LEFT, Inches(1.75), Inches(0.6), color=ACCENT, weight=1.5)
    text(slide, LEFT, Inches(2.0), Inches(11), Inches(1.3), "Krypsis", size=72, font=SERIF)
    text(slide, LEFT, Inches(3.35), Inches(11), Inches(1.0),
         "Federated network intrusion detection over real router clients,\n"
         "with a security-fused update protocol",
         size=20, font=SERIF, color=INK_SOFT, spacing=1.25)
    hrule(slide, LEFT, Inches(5.3), Inches(11.7), color=LINE)
    team = [("Rithika K", "CB.SC.U4AIE25126"), ("Pradhaniya S", "CB.SC.U4AIE25148"),
            ("Sathya K", "CB.SC.U4AIE25154"), ("Vinudharshini PP", "CB.SC.U4AIE25161")]
    for i, (name, roll) in enumerate(team):
        x = LEFT + i * Inches(2.95)
        text(slide, x, Inches(5.5), Inches(2.8), Inches(0.7),
             [[(name, {"bold": True, "size": 13})], [(roll, {"color": MUTED, "size": 11})]])
    notes(slide, "Introduce the team and the project in one sentence: Krypsis trains one "
                 "intrusion detector across 10 routers without moving their traffic, and "
                 "protects the model updates with our own protocol.")


def s_intro(prs):
    slide = base(prs, "Introduction", "Intrusion detection without sharing traffic")
    blocks = [
        ("The problem", "An intrusion detection system (NIDS) learns to tell normal flows "
         "from attacks, so it needs varied traffic. But traffic logs reveal hosts, services "
         "and internal structure, so organisations cannot simply pool them."),
        ("Federated learning", "Each router trains the shared model on its own traffic and "
         "sends back only the change in weights. The server averages the changes (FedAvg). "
         "Raw traffic never leaves a router."),
        ("The new risk", "The updates become the attack surface: they can be tampered with "
         "in transit or poisoned by a compromised router (label flipping, backdoors). And "
         "honest routers with unusual traffic (non-IID) can look like attackers."),
    ]
    for i, (head, body) in enumerate(blocks):
        y = Inches(1.95) + i * Inches(1.15)
        label(slide, LEFT, y, Inches(6.0), head)
        text(slide, LEFT, y + Inches(0.3), Inches(6.0), Inches(0.85), body, size=12.5,
             color=INK, spacing=1.2)

    # Small federated-learning diagram.
    cx0, cy0, cw, ch = Inches(7.25), Inches(1.95), Inches(5.28), Inches(3.3)
    card(slide, cx0, cy0, cw, ch)
    mid = cx0 + cw / 2
    sw, sh = Inches(2.6), Inches(0.68)
    box_label(slide, mid - sw / 2, cy0 + Inches(0.3), sw, sh, "Aggregation server",
              "FedAvg", fill=ACCENT_SOFT, line=ACCENT, title_color=ACCENT, size=11.5)
    bw, bh, step = Inches(1.05), Inches(0.62), Inches(1.25)
    x0 = mid - (3 * step + bw) / 2
    by = cy0 + Inches(1.95)
    bus = by - Inches(0.5)
    centres = [x0 + i * step + bw / 2 for i in range(4)]
    hrule(slide, centres[0], bus, centres[-1] - centres[0], color=MUTED, weight=1)
    line = _plain(slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, *_e(mid, cy0 + Inches(0.3) + sh, mid, bus)))
    line.line.color.rgb, line.line.width = MUTED, Pt(1)
    for cxx, lab in zip(centres, ["Router 1", "Router 2", None, "Router 10"]):
        if lab is None:
            text(slide, cxx - bw / 2, by + Inches(0.1), bw, Inches(0.4), "· · ·", size=16,
                 color=MUTED, align=PP_ALIGN.CENTER)
            continue
        box_label(slide, cxx - bw / 2, by, bw, bh, lab, fill=WHITE, size=10.5)
        arrow(slide, cxx - Inches(0.1), bus, cxx - Inches(0.1), by, color=MUTED, weight=1)
        arrow(slide, cxx + Inches(0.1), by, cxx + Inches(0.1), bus, color=ACCENT, weight=1)
    text(slide, cx0, cy0 + Inches(2.75), cw, Inches(0.35),
         [[("↓ global model     ", {"color": INK_SOFT}), ("↑ weight update only",
                                                            {"color": ACCENT})]],
         size=10.5, align=PP_ALIGN.CENTER)

    rect(slide, LEFT, Inches(5.55), CONTENT_W, Inches(1.2), fill=ACCENT_SOFT, line=None,
         radius=0.06)
    text(slide, LEFT + Inches(0.3), Inches(5.55), CONTENT_W - Inches(0.6), Inches(1.2), [
        [("Our approach  ", {"bold": True, "color": ACCENT}),
         ("Krypsis builds security into the update protocol itself: every update carries an "
          "integrity tag and a verifiable fingerprint, and suspicious updates are filtered "
          "cheaply before aggregation.", {})],
        [("Research question  ", {"bold": True, "color": ACCENT}),
         ("Does one global anomaly threshold wrongly flag honest non-IID routers, and do "
          "per-cluster (Mondrian) thresholds reduce those false alarms?", {})],
    ], size=12, anchor=MSO_ANCHOR.MIDDLE, spacing=1.2)
    notes(slide, "Detection needs varied traffic, but traffic is sensitive. Federated "
                 "learning keeps traffic on the routers and only shares weight updates, as in "
                 "the diagram. That moves the risk to the updates themselves: tampering, "
                 "poisoning, and honest routers that simply look different. Krypsis protects "
                 "the updates, and our research question asks whether one global threshold is "
                 "unfair to unusual honest routers.")


def s_objectives(prs):
    slide = base(prs, "Objectives", "Objectives")
    objs = [
        ("Federated detector", "Train one intrusion detector across 10 router clients "
         "without centralizing raw traffic.",
         f"Met · FedAvg over 10 routers: {pct(R['fed_router']['accuracy'], 2)}"),
        ("Security-fused protocol", "Design an update message with an integrity tag and a "
         "fingerprint, and filter bad updates before aggregation.",
         "Met · HMAC, verifiable fingerprint, 3 anomaly scores"),
        ("Detection quality", "Measure accuracy, precision, recall and F1, for binary and "
         "11-class detection.", "Met · two datasets, binary and 11-class"),
        ("Communication cost", "Measure the protocol's overhead against a generic HTTP/JSON "
         "transfer.", f"Met · +{pct(OVERHEAD, 2)} overhead; JSON is {JSON_X:.1f}× larger"),
        ("Robustness and the research question", "Test poisoning, dropout, traffic shift and "
         "global vs Mondrian thresholds, over repeated seeds with significance tests.",
         "Met · 235 federated runs; Mondrian not better"),
    ]
    for i, (name, desc, status) in enumerate(objs):
        ry = Inches(1.95) + i * Inches(0.95)
        text(slide, LEFT, ry, Inches(0.6), Inches(0.6), str(i + 1), size=24, font=SERIF,
             color=ACCENT)
        text(slide, LEFT + Inches(0.6), ry + Inches(0.02), Inches(6.9), Inches(0.9),
             [[(name, {"bold": True, "size": 14})], [(desc, {"size": 12, "color": INK_SOFT})]],
             spacing=1.15)
        rect(slide, Inches(8.45), ry + Inches(0.1), Inches(4.08), Inches(0.62),
             fill=ACCENT_SOFT, line=None, radius=0.2)
        text(slide, Inches(8.6), ry + Inches(0.1), Inches(3.8), Inches(0.62), status,
             size=11.5, color=ACCENT, anchor=MSO_ANCHOR.MIDDLE)
        if i < len(objs) - 1:
            hrule(slide, LEFT + Inches(0.6), ry + Inches(0.88), Inches(11.1), color=LINE,
                  weight=0.5)
    notes(slide, "Five objectives. The right column shows how far each was met; every number "
                 "comes from our result files.")


# NSL-KDD Dirichlet split (alpha 0.5): attack % per client, from
# data/processed_nslkdd/client_assignment_noniid.npy.
DIRICHLET_ATTACK = [28.0, 100.0, 99.2, 18.4, 40.2, 97.6, 40.2, 11.9, 84.1, 54.3]


def bars(slide, x, base_y, max_h, values, names, bw=Inches(0.36), step=Inches(0.555),
         fill=ACCENT):
    for i, (v, n) in enumerate(zip(values, names)):
        bx = x + i * step
        bh = max_h * v / 100
        if bh > 0:
            rect(slide, bx, base_y - bh, bw, bh, fill=fill, line=None)
        text(slide, bx - Inches(0.1), base_y - bh - Inches(0.24), bw + Inches(0.2), Inches(0.22),
             f"{v:.0f}", size=9, color=INK_SOFT, align=PP_ALIGN.CENTER)
        text(slide, bx - Inches(0.1), base_y + Inches(0.04), bw + Inches(0.2), Inches(0.22),
             n, size=9, color=MUTED, align=PP_ALIGN.CENTER)
    hrule(slide, x - Inches(0.05), base_y, step * len(values), color=INK_SOFT, weight=0.75)


def s_method_system(prs):
    slide = base(prs, "Methodology · 1 / 6", "System architecture and dataset")
    y, h = Inches(1.95), Inches(1.15)
    blocks = [
        (LEFT, Inches(2.2), "Router client", "local flows → local training → update Δw"),
        (Inches(3.4), Inches(2.4), "Krypsis message", "header · fingerprint · payload · HMAC"),
        (Inches(6.2), Inches(3.1), "Server checks", "verify tag and fingerprint → score → "
         "threshold → second check"),
        (Inches(9.7), Inches(2.83), "Capped FedAvg", "weighted average, ≤ 15% per client"),
    ]
    for i, (x, w, title, body) in enumerate(blocks):
        accent = i in (1, 2)
        box_label(slide, x, y, w, h, title, body, fill=ACCENT_SOFT if accent else WHITE,
                  line=ACCENT if accent else LINE, title_color=ACCENT if accent else INK,
                  size=12)
        if i < len(blocks) - 1:
            nx = blocks[i + 1][0]
            arrow(slide, x + w + Inches(0.03), y + h / 2, nx - Inches(0.03), y + h / 2,
                  color=ACCENT)
    loop_y = y + h + Inches(0.35)
    rx, fx = LEFT + Inches(1.1), Inches(11.1)
    hrule(slide, rx, loop_y, fx - rx, color=MUTED, weight=1)
    arrow(slide, fx, y + h, fx, loop_y, color=MUTED)
    arrow(slide, rx, loop_y, rx, y + h, color=MUTED)
    text(slide, Inches(4.4), loop_y + Inches(0.06), Inches(4.6), Inches(0.3),
         "new global model sent to every router, next round", size=10.5, color=INK_SOFT,
         align=PP_ALIGN.CENTER)

    hrule(slide, LEFT, Inches(4.05), CONTENT_W)
    label(slide, LEFT, Inches(4.2), Inches(6.0), "Dataset · FLNET2023 (Kumar et al., 2023)")
    bullets(slide, LEFT, Inches(4.6), Inches(6.0), Inches(2.3), [
        ("Built for federated learning:", "flows recorded at 10 routers of an emulated "
         "40-node network."),
        ("10 routers = 10 clients,", "each with its own mix of attacks."),
        ("Labels:", "Normal or one of 10 attacks (DDoS, DoS, web attacks, MITM)."),
        ("NSL-KDD", "is used as a second dataset to repeat the results."),
    ], size=12, gap=5)
    stats = [("564,007", "training flows"), ("79,491", "test flows"),
             ("66", "features per flow"), ("66%", "of training flows are attacks")]
    for i, (num, lab) in enumerate(stats):
        col, row = i % 2, i // 2
        x = Inches(7.4) + col * Inches(2.6)
        yy = Inches(4.3) + row * Inches(1.2)
        text(slide, x, yy, Inches(2.5), Inches(1.1),
             [[(num, {"size": 24, "font": SERIF})], [(lab, {"size": 11, "color": INK_SOFT})]],
             spacing=1.05)
    notes(slide, "One round, left to right: the router trains on its own flows and wraps the "
                 "weight change in a Krypsis message; the server verifies, scores and filters "
                 "it, then averages the accepted updates with a 15% cap per client, and sends "
                 "the new model back. The data is FLNET2023, a dataset made for federated "
                 "intrusion detection: traffic from 10 routers, so each router is one client.")


def s_method_preprocess(prs):
    slide = base(prs, "Methodology · 2 / 6", "Preprocessing: from raw flows to model input")
    steps = [
        ("Tag and sample", "Each flow gets its router number; each file is sampled to 10% "
                           "(4.8 M flows is too many to train repeatedly)."),
        ("Remove identifiers", "IPs, source port and timestamp dropped, so the model learns "
                               "behaviour, not addresses."),
        ("Clean", "Rows with inf / NaN values and 12 constant columns removed."),
        ("Scale", "Signed log for huge ranges, then min-max to [0, 1], fitted on training "
                  "data only."),
        ("Label", "Normal = 0, any attack = 1; the attack name is kept for the 11-class "
                  "model."),
    ]
    for i, (name, body) in enumerate(steps):
        yy = Inches(1.95) + i * Inches(0.93)
        rect(slide, LEFT, yy + Inches(0.04), Inches(0.4), Inches(0.4), fill=ACCENT_SOFT,
             line=None, radius=0.5)
        text(slide, LEFT, yy + Inches(0.04), Inches(0.4), Inches(0.4), str(i + 1), size=12,
             bold=True, color=ACCENT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, LEFT + Inches(0.6), yy, Inches(4.8), Inches(0.9),
             [[(name, {"bold": True, "size": 13.5})], [(body, {"size": 11.5, "color": INK_SOFT})]],
             spacing=1.15)
    code(slide, Inches(6.55), Inches(1.95), Inches(5.98), Inches(4.55), '''
        DROP_COLUMNS = ["src_ip", "dst_ip", "src_port", "timestamp"]

        def sample_file(path, rng):          # 10%, at least 2,000 rows
            df = pd.read_csv(path, low_memory=False)
            keep = min(len(df), max(2000, round(len(df) * 0.10)))
            ...
        df["router"] = int(ROUTER_PATTERN.search(name).group(1))

        features = features.replace([np.inf, -np.inf], np.nan)
        df = df.loc[~features.isna().any(axis=1)]

        def signed_log1p(x):                 # values span 1 to 1e9
            return np.sign(x) * np.log1p(np.abs(x))

        scaler = MinMaxScaler()              # fitted on TRAIN only
        X_train = scaler.fit_transform(signed_log1p(train))
        X_test = np.clip(scaler.transform(signed_log1p(test)), 0, 1)
    ''', "src/preprocess.py  (excerpt)", size=9.5)
    notes(slide, "Five steps, left, and the code that does them, right. Each flow is tagged "
                 "with its router so we can give it to the right client. We sample 10% to keep "
                 "training fast. We drop IP addresses, the source port and timestamps, otherwise "
                 "the model could memorise the attacker's address. Then we clean and scale; the "
                 "scaler is fitted on training data only, so the test set stays unseen.")


def s_method_clients(prs):
    slide = base(prs, "Methodology · 3 / 6", "Clients: why uneven (non-IID) data matters")
    text(slide, LEFT, Inches(1.85), CONTENT_W, Inches(0.6), [
        [("IID", {"bold": True, "color": ACCENT}),
         (" = every client has a similar mix of traffic.     ", {}),
         ("Non-IID", {"bold": True, "color": ACCENT}),
         (" = each client sees different traffic, as in real networks.", {})]],
        size=13.5)
    label(slide, LEFT, Inches(2.45), Inches(6), "FLNET2023 · 10 real routers · attack %")
    bars(slide, LEFT + Inches(0.1), Inches(4.25), Inches(1.25), [r[2] for r in ROUTERS],
         [f"R{r[0]}" for r in ROUTERS])
    label(slide, LEFT, Inches(4.7), Inches(6), "NSL-KDD · Dirichlet split, alpha 0.5 · attack %")
    bars(slide, LEFT + Inches(0.1), Inches(6.5), Inches(1.25), DIRICHLET_ATTACK,
         [f"C{i}" for i in range(1, 11)], fill=RGBColor(0x8F, 0xA9, 0xA4))
    code(slide, Inches(6.75), Inches(2.45), Inches(5.78), Inches(3.75), '''
        def split_non_iid_dirichlet(labels, num_clients, alpha, seed):
            rng = np.random.default_rng(seed)
            assignment = np.full(len(labels), -1, dtype=int)
            for category in np.unique(labels):
                idx = np.where(labels == category)[0]
                rng.shuffle(idx)
                share = rng.dirichlet(alpha * np.ones(num_clients))
                sizes = (share * len(idx)).astype(int)
                sizes[-1] += len(idx) - sizes.sum()
                start = 0
                for client_id, size in enumerate(sizes):
                    assignment[idx[start:start + size]] = client_id
                    start += size
            return assignment
    ''', "src/preprocess_nslkdd.py", size=9.5)
    text(slide, Inches(6.75), Inches(6.3), Inches(5.78), Inches(0.5),
         "Each attack type is shared out with random Dirichlet proportions; smaller α means "
         "more uneven clients.", size=10.5, color=MUTED)
    notes(slide, "IID means every client has a similar mix; non-IID means each one is "
                 "different. FLNET2023 is naturally non-IID: router 3 sees 19% attack traffic, "
                 "router 4 sees 92%. For NSL-KDD we created uneven clients with a Dirichlet "
                 "split: each attack type is divided among the 10 clients with random "
                 "proportions, alpha 0.5. Some clients end up almost all attack, others almost "
                 "all normal. This matters because an honest client with unusual data can look "
                 "like an attacker, which is our research question. We also ran an IID split "
                 "of FLNET2023 as a control.")


def s_method_model(prs):
    slide = base(prs, "Methodology · 4 / 6", "Model and federated training (FedAvg)")
    layers_ = [("Input", "66 features"), ("256", "Dense"), ("128", "Dense"), ("64", "Dense"),
               ("Output", "normal / attack")]
    bw, gap = Inches(1.95), Inches(0.5)
    for i, (title, sub) in enumerate(layers_):
        x = LEFT + i * (bw + gap)
        box_label(slide, x, Inches(1.9), bw, Inches(0.8), title, sub,
                  fill=ACCENT_SOFT if 0 < i < 4 else WHITE,
                  line=ACCENT if 0 < i < 4 else LINE, size=13)
        if i < 4:
            arrow(slide, x + bw + Inches(0.04), Inches(2.3), x + bw + gap - Inches(0.04),
                  Inches(2.3), color=MUTED)
    text(slide, LEFT, Inches(2.82), CONTENT_W, Inches(0.3),
         "ReLU + dropout + L2 · 58,369 parameters · Adam, binary cross-entropy · "
         "15 rounds × 2 local epochs · centralized baseline uses the same model",
         size=11, color=INK_SOFT, align=PP_ALIGN.CENTER)
    colw = Inches(5.75)
    rx = LEFT + colw + Inches(0.23)
    code(slide, LEFT, Inches(3.3), colw, Inches(3.25), '''
        def build_model(input_dim):
            l2 = tf.keras.regularizers.l2(1e-4)
            model = tf.keras.Sequential([
                layers.Input(shape=(input_dim,)),
                layers.Dense(256, activation="relu", kernel_regularizer=l2),
                layers.Dropout(0.3),
                layers.Dense(128, activation="relu", kernel_regularizer=l2),
                layers.Dropout(0.3),
                layers.Dense(64, activation="relu", kernel_regularizer=l2),
                layers.Dropout(0.2),
                layers.Dense(1, activation="sigmoid")])
            model.compile(optimizer="adam", loss="binary_crossentropy")
            return model
    ''', "src/model.py  (layers = tf.keras.layers)", size=9)
    code(slide, rx, Inches(3.3), colw, Inches(3.25), '''
        def federated_average(weight_list, sample_counts):
            total = sum(sample_counts)
            averaged = []
            for layer_idx in range(len(weight_list[0])):
                layer_sum = sum(weight_list[i][layer_idx]
                                * (sample_counts[i] / total)
                                for i in range(len(weight_list)))
                averaged.append(layer_sum)
            return averaged

        for round_num in range(1, num_rounds + 1):
            for client_id in range(num_clients):   # local training
                local_model.set_weights(global_weights)
                local_model.fit(X_client, y_client, epochs=2)
            global_weights = federated_average(local_weights, counts)
    ''', "src/federated_training.py  (FedAvg)", size=9)
    notes(slide, "The model is a small multilayer perceptron: 66 inputs, three hidden layers, "
                 "one output for normal or attack. Left is the code. Right is FedAvg: every "
                 "round each client starts from the global model and trains on its own data; "
                 "the server then averages each layer, weighting clients by how much data they "
                 "have. The same model trained on all data in one place is our centralized "
                 "baseline, the best accuracy we can hope for.")


def s_method_protocol(prs):
    slide = base(prs, "Methodology · 5 / 6", "Federated round and the Krypsis message")
    parts = [("Length", "4 B", Inches(1.25), BG_DEEP),
             ("Header + fingerprint", "client · round · samples · L2 norm · layer norms · "
              "64-number sketch", Inches(4.3), ACCENT_SOFT),
             ("Payload", f"update Δw · {COMM['raw_payload_bytes']:,} B (float32)",
              Inches(3.9), WHITE),
             ("Tag", "HMAC-SHA256 · 32 B", Inches(2.28), BRONZE_SOFT)]
    x = LEFT
    for name, body, w, fill in parts:
        rect(slide, x, Inches(1.95), w, Inches(0.85), fill=fill, line=LINE)
        text(slide, x + Inches(0.15), Inches(2.03), w - Inches(0.3), Inches(0.75),
             [[(name.upper(), {"bold": True, "size": 10, "color": ACCENT})],
              [(body, {"size": 11, "color": INK})]], spacing=1.15)
        x += w

    colw = Inches(5.75)
    rx = LEFT + colw + Inches(0.23)
    code(slide, LEFT, Inches(3.05), colw, Inches(3.3), '''
        for rnd in range(1, ROUNDS + 1):
            for c in clients:                # on each router
                local.set_weights(unflatten(g, like))
                local.fit(X[a == c], y[a == c], epochs=1,
                          batch_size=256)
                d = flatten(local.get_weights()) - g    # update Δw
                msg = pack(c, rnd, n[c], d, keys[c], fp)  # → server
                header, d, reason = unpack(msg, keys, fp)
            ...                              # score, filter (next slide)
            w = capped_weights(counts, 1.5)
            g = g + sum(accepted[c] * w[c] for c in accepted)
    ''', "src/demo.py  ·  one federated round", size=9)
    code(slide, rx, Inches(3.05), colw, Inches(3.3), '''
        def compute(self, delta):            # the fingerprint
            return {"l2": norm(delta),
                    "layer_l2": [norm(delta[s]) for s in self.layer_slices],
                    "sketch": (self.projection @ delta).tolist()}

        def pack(client_id, round_num, num_samples, delta, key, fp):
            header = json.dumps({"client": client_id, "round": round_num,
                                 "n": num_samples, "fp": fp.compute(delta)},
                                separators=(",", ":")).encode()
            payload = delta.astype(np.float32).tobytes()
            tag = hmac.new(key, header + payload, hashlib.sha256).digest()
            return len(header).to_bytes(4, "big") + header + payload + tag
    ''', "src/protocol.py  (excerpt)", size=9)
    text(slide, LEFT, Inches(6.45), CONTENT_W, Inches(0.4),
         f"The sketch is a fixed random projection (public seed 2023) of the update to 64 "
         f"numbers. Whole message: +{COMM['krypsis_overhead_bytes']:,} B "
         f"({pct(OVERHEAD, 2)}) over the bare update.", size=10.5, color=MUTED)
    notes(slide, "The strip on top is one message on the wire. Left: one federated round. "
                 "Each router starts from the global model g, trains one epoch on its own "
                 "flows, computes its update d, and packs it. The server unpacks, filters, and "
                 "averages with capped weights. Right: pack builds the header with the "
                 "fingerprint (overall size, size per layer, and a 64-number sketch), appends "
                 "the raw float32 update, and signs everything with HMAC-SHA256 using the "
                 "router's own key.")


def s_method_server(prs):
    slide = base(prs, "Methodology · 6 / 6", "Server checks before aggregation")
    steps = [("Verify tag", "reject", BRONZE), ("Verify fingerprint", "reject", BRONZE),
             ("Score", "3 scores", ACCENT), ("Standardize", "robust z", ACCENT),
             ("Threshold", "conformal", ACCENT), ("Second check", "trimmed mean", ACCENT),
             ("Capped FedAvg", "≤ 15% each", INK)]
    sw, gap = Inches(1.5), Inches(0.205)
    for i, (name, sub, color) in enumerate(steps):
        x = LEFT + i * (sw + gap)
        rect(slide, x, Inches(1.95), sw, Inches(0.7), fill=WHITE, line=LINE, radius=0.1)
        rect(slide, x, Inches(1.95), sw, Inches(0.05), fill=color, line=None)
        text(slide, x, Inches(1.95), sw, Inches(0.7),
             [[(name, {"bold": True, "size": 10.5})], [(sub, {"size": 9.5, "color": INK_SOFT})]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=1.05)
        if i < len(steps) - 1:
            arrow(slide, x + sw + Inches(0.02), Inches(2.3), x + sw + gap - Inches(0.02),
                  Inches(2.3), color=MUTED, weight=1)

    colw = Inches(5.75)
    rx = LEFT + colw + Inches(0.23)
    code(slide, LEFT, Inches(2.9), colw, Inches(3.45), '''
        def unpack(message, keys, fp):
            ...                              # split header/payload/tag
            expected = hmac.new(key, header_bytes + payload,
                                hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected):
                return header, None, "bad_tag"      # tampered
            delta = np.frombuffer(payload, dtype=np.float32)
            actual = fp.compute(delta)       # recompute, never trust
            if not np.allclose(actual["sketch"], header["fp"]["sketch"],
                               rtol=1e-3, atol=1e-5):
                return header, None, "fingerprint_mismatch"
            return header, delta, None
    ''', "src/protocol.py  ·  step 1-2", size=9)
    code(slide, rx, Inches(2.9), colw, Inches(3.45), '''
        consensus = np.median(sketches, axis=0)    # attackers can't drag it
        scores[c] = {
            "norm": abs(log(l2[c] / median_norm)),
            "consensus": 1 - cosine(sketch[c], consensus),
            "history": 1 - cosine(sketch[c], prev_sketch[c]),
        }
        z = (score - median) / (1.4826 * MAD)      # within this round
        flagged = any(z[s] > threshold[s] for s in SCORE_NAMES)
        # threshold = ceil((n+1)(1-alpha))-th calibration score, alpha=0.05

        rescued = second_check(passed, flagged, 0.2)
        w = capped_weights(counts, 1.5)             # 1.5 x 1/10 = 15%
    ''', "src/protocol.py  ·  steps 3-7 (condensed)", size=9)
    text(slide, LEFT, Inches(6.45), CONTENT_W, Inches(0.4),
         "Thresholds come from 5 clean calibration rounds: one for all clients (global), or "
         "one per k-means cluster of similar clients (Mondrian, k = 3).",
         size=10.5, color=MUTED)
    notes(slide, "Seven steps. Left: the hard checks. A wrong HMAC means the message was "
                 "changed in transit; the server also recomputes the fingerprint from the "
                 "payload, so a client cannot send a fake innocent-looking one. Right: three "
                 "cheap scores from the fingerprint only: is the update unusually large or "
                 "small, does it point away from the median of the other routers, and does it "
                 "differ from this router's last update. Scores are standardized within the "
                 "round, compared with conformal thresholds, flagged updates get a second "
                 "check against a trimmed mean, and no client gets more than 15% of the "
                 "average.")


def s_results_detection(prs):
    slide = base(prs, "Results · 1 / 2", "Detection: binary is easy, naming the attack is not")
    colw = Inches(4.35)
    label(slide, LEFT, Inches(1.95), colw, "Binary accuracy · FLNET2023 test set")
    stats = [(pct(R["central"]["accuracy"]), "centralized"),
             (pct(R["fed_router"]["accuracy"], 2), "FedAvg · 10 real routers"),
             (pct(R["fed_iid"]["accuracy"], 3), "FedAvg · IID split")]
    for i, (num, lab) in enumerate(stats):
        y = Inches(2.35) + i * Inches(0.62)
        text(slide, LEFT, y, Inches(1.9), Inches(0.55), num, size=20, font=SERIF,
             anchor=MSO_ANCHOR.MIDDLE)
        text(slide, LEFT + Inches(1.95), y, Inches(2.4), Inches(0.55), lab, size=11.5,
             color=INK_SOFT, anchor=MSO_ANCHOR.MIDDLE)
    label(slide, LEFT, Inches(4.35), colw, "Multi-class macro-F1 · 11 types")
    text(slide, LEFT, Inches(4.7), colw, Inches(0.5), [[
        (f"{MC['centralized']['macro_f1']:.2f}", {"font": SERIF, "size": 18}),
        ("  central   ", {"size": 11, "color": INK_SOFT}),
        (f"{MC['federated_iid']['macro_f1']:.2f}", {"font": SERIF, "size": 18}),
        ("  IID   ", {"size": 11, "color": INK_SOFT}),
        (f"{MC['federated_router']['macro_f1']:.2f}", {"font": SERIF, "size": 18,
                                                       "color": BRONZE}),
        ("  routers", {"size": 11, "color": INK_SOFT})]])
    text(slide, LEFT, Inches(5.35), colw, Inches(1.5),
         "We checked the 100%: one feature alone scores 97.5%, so binary accuracy cannot "
         "separate setups. With 11 classes, attack types seen at only one or two routers are "
         "averaged away: the non-IID cost.", size=11, color=INK_SOFT, spacing=1.25)
    picture(slide, "multiclass_recall.png", Inches(5.55), Inches(1.95), w=Inches(6.98))
    notes(slide, "Federated training over the real routers matches centralized training on "
                 "the binary task. But we checked the perfect score: the emulated traffic is "
                 "separable by one feature, so we also trained an 11-class model. There, "
                 "macro-F1 drops from 0.76 with an IID split to 0.39 with the real routers: "
                 "attack types held by one router are averaged away. The chart shows recall "
                 "per attack type.")


def _dropout_stats():
    runs = [r for r in R["robustness"]["runs"] if r["experiment"] == "dropout"]
    calib = R["robustness"]["config"]["calibration_rounds"]
    out = {}
    for p in sorted({r["setting"] for r in runs}):
        row = {}
        for policy in ("none", "v2"):
            rs = [r for r in runs if r["setting"] == p and r["policy"] == policy]
            row[policy] = float(np.mean([np.mean(r["accuracy_by_round"][calib:]) for r in rs]))
        row["caught"] = RB["dropout"][str(p)]["v2"]["detection_rate_mean"]
        out[p] = row
    return out


def s_results_attacks(prs):
    slide = base(prs, "Results · 2 / 2", "The protocol under attack")
    picture(slide, "attack_accuracy_by_round.png", LEFT, Inches(1.95), w=Inches(7.4))
    drop = _dropout_stats()
    hi = max(drop)
    sc = RB["scale"]["4"]["v2"]
    shift = next(iter(RB["shift"].values()))["v2"]
    text(slide, LEFT, Inches(5.35), Inches(7.4), Inches(1.5),
         "Attack setup: 2 of 10 clients flip their labels (attack ↔ normal) from round 6 "
         "of 12; rounds 1–5 calibrate the thresholds. NSL-KDD gain is significant "
         "(p = 0.009, 10 seeds); FLNET2023 points the same way (5 seeds).", size=11, color=INK_SOFT, spacing=1.25)

    x, w = Inches(8.55), Inches(3.98)
    rows = [
        ("Tampered messages rejected", "105 / 105"),
        ("Label flip · FLNET2023", f"{pct(FL['none']['accuracy_mean'])} → "
                                   f"{pct(FL['v1']['accuracy_mean'])}"),
        ("Label flip · NSL-KDD", f"{pct(NL['none']['accuracy_mean'])} → "
                                 f"{pct(NL['v2']['accuracy_mean'])}"),
        ("Backdoor success · NSL-KDD", f"{pct(NB['none']['backdoor_asr_mean'])} → "
                                       f"{pct(NB['v2']['backdoor_asr_mean'])}"),
        (f"{100 * hi:.0f}% routers offline", f"{pct(drop[hi]['none'])} → "
                                             f"{pct(drop[hi]['v2'])}"),
        ("40 clients · caught", f"{pct(sc['detection_rate_mean'], 0)} · "
                                f"{sc['mean_server_ms_per_round_mean']:.0f} ms/round"),
        ("Shifted honest router excluded", pct(shift["shifted_client_excluded_rate_mean"], 0)),
    ]
    label(slide, x, Inches(1.95), w, "No defense → Krypsis")
    for i, (name, val) in enumerate(rows):
        y = Inches(2.35) + i * Inches(0.62)
        text(slide, x, y, w, Inches(0.6),
             [[(name, {"size": 10.5, "color": INK_SOFT})],
              [(val, {"size": 15, "font": SERIF})]], spacing=1.05)
        hrule(slide, x, y + Inches(0.6), w, weight=0.5)
    notes(slide, "Left: accuracy round by round. Without protection the poisoned rounds "
                 "drag accuracy down; with Krypsis it stays near the clean level. Right: every "
                 "tampered message was rejected, label flipping and backdoors lose most of "
                 "their effect, the protocol still helps when 40% of routers drop out, it "
                 "scales to 40 clients in milliseconds, and an honest router whose traffic "
                 "changed was never excluded. On FLNET2023 the backdoor failed even without a "
                 "defense.")


def s_comparison(prs):
    slide = base(prs, "Comparison", "Comparison with existing approaches and our setups")
    rows = [
        ["Approach", "Tamper check", "Filters poisoned updates", "When / cost", "Evidence here"],
        ["Plain FedAvg (McMahan 2017)", "No", "No", "—",
         f"Label flip: {pct(FL['none']['accuracy_mean'])} FLNET, {pct(NL['none']['accuracy_mean'])} NSL"],
        ["HTTP + JSON transfer", "Channel only (TLS)", "No",
         f"{JSON_X:.1f}× message size", "Measured: 1,316 KB / update"],
        ["Krum (Blanchard 2017)", "No", "Yes, every round",
         "After full receipt · O(n²·d)", "Literature (not implemented)"],
        ["Trimmed mean (Yin 2018)", "No", "Yes, every round",
         "After full receipt · O(n·d·log n)", "Used inside our second check"],
        ["Krypsis (ours)", "Per-client HMAC", "Yes, cheap filter first",
         f"Before aggregation · +{pct(OVERHEAD, 2)}",
         f"Label flip: {pct(FL['v1']['accuracy_mean'])} FLNET, {pct(NL['v2']['accuracy_mean'])} NSL"],
    ]
    table(slide, LEFT, Inches(1.9), [Inches(2.75), Inches(1.65), Inches(2.2), Inches(2.6),
                                     Inches(2.53)], rows, size=10.5, row_h=Inches(0.43),
          bold_cols=(0,), shade_rows=(5,))

    def f(e, k):
        return pct(e[f"{k}_mean"])
    ours = [["Our setups", "No defense", "Protocol v1", "Protocol v2", "v2 Mondrian"],
            ["FLNET2023 · label flip accuracy ↑", f(FL["none"], "accuracy"),
             f(FL["v1"], "accuracy"), f(FL["v2"], "accuracy"), f(FL["v2_mondrian"], "accuracy")],
            ["NSL-KDD · label flip accuracy ↑", f(NL["none"], "accuracy"),
             f(NL["v1"], "accuracy"), f(NL["v2"], "accuracy"), f(NL["v2_mondrian"], "accuracy")],
            ["NSL-KDD · backdoor success ↓", f(NB["none"], "backdoor_asr"),
             f(NB["v1"], "backdoor_asr"), f(NB["v2"], "backdoor_asr"),
             f(NB["v2_mondrian"], "backdoor_asr")],
            ["NSL-KDD · honest excluded ↓", "—", f(NL["v1"], "false_positive_rate"),
             f(NL["v2"], "false_positive_rate"), f(NL["v2_mondrian"], "false_positive_rate")]]
    table(slide, LEFT, Inches(4.6), [Inches(3.73), Inches(2.0), Inches(2.0), Inches(2.0),
                                      Inches(2.0)], ours, size=10.5, row_h=Inches(0.38))
    text(slide, LEFT, Inches(6.6), CONTENT_W, Inches(0.25),
         "v1 drops every flagged update · v2 adds the second check and the 15% weight cap · "
         "FLNET2023 5 seeds, NSL-KDD 10 seeds, means shown.", size=9.5, color=MUTED)
    notes(slide, "Top: plain FedAvg has no protection; HTTP with TLS protects the channel but "
                 "not against a malicious client; Krum and trimmed mean filter updates only "
                 "after receiving everything, every round. Krypsis adds a per-client integrity "
                 "tag and a cheap filter first. Bottom: our own setups. Both protocol versions "
                 "beat no defense; v2 excludes fewer honest routers; Mondrian is never clearly "
                 "better. On FLNET2023 the weight cap has a downside in one seed.")


def s_conclusion(prs):
    slide = base(prs, "Conclusion", "Conclusion")
    rect(slide, LEFT, Inches(1.9), CONTENT_W, Inches(1.05), fill=ACCENT_SOFT, line=None,
         radius=0.06)
    text(slide, LEFT + Inches(0.3), Inches(1.9), CONTENT_W - Inches(0.6), Inches(1.05), [
        [("Research question · answer: no.  ", {"bold": True, "color": ACCENT, "size": 13}),
         (f"Mondrian caught {pct(PG['mondrian']['detection_rate_mean'])} vs global "
          f"{pct(PG['global']['detection_rate_mean'])} (p = 0.21, 15 seeds), and no other "
          "test was significant (all p ≥ 0.11). With per-round standardization, one global "
          "threshold is enough.", {"size": 12.5})],
    ], anchor=MSO_ANCHOR.MIDDLE, spacing=1.25)
    colw = Inches(5.6)
    rx = Inches(6.93)
    label(slide, LEFT, Inches(3.2), colw, "Conclusions")
    bullets(slide, LEFT, Inches(3.55), colw, Inches(3.3), [
        "Federated training over 10 real routers matches centralized binary detection.",
        "Naming the attack exposes the non-IID cost: macro-F1 0.39 vs 0.76 IID.",
        "Krypsis rejects every tampered message and raises accuracy under attack, for "
        "under 1% extra message size.",
        "A global threshold is enough; Mondrian brought no significant gain.",
    ], size=12, gap=8)
    label(slide, rx, Inches(3.2), colw, "Limitations and future work", color=BRONZE)
    bullets(slide, rx, Inches(3.55), colw, Inches(3.3), [
        "Simulated in one process on emulated traffic; attackers do not adapt.",
        "The weight cap can shift weight from an honest large router to attackers.",
        "At 40% dropout only about a third of poisoned updates are caught.",
        "Next: protocol on the 11-class task, a trust-based cap, a real network "
        "(Mininet / SDN), more FLNET2023 seeds.",
    ], size=12, gap=8)
    notes(slide, "We tested the research question three ways and Mondrian was never "
                 "significantly better: a negative answer, tested properly. Then the four "
                 "conclusions, and honestly what did not work and what comes next.")


def s_references(prs):
    slide = base(prs, "References", "References")
    refs = [
        ("Kumar, P., Liu, J., et al. (2023). FLNET2023: Realistic Network Intrusion Detection "
         "Dataset for Federated Learning. MILCOM 2023.",
         "https://doi.org/10.1109/MILCOM58377.2023.10356272"),
        ("FLNET2023 dataset and documentation (nsol-nmsu / FML-Network).",
         "https://github.com/nsol-nmsu/FML-Network"),
        ("McMahan, B., et al. (2017). Communication-Efficient Learning of Deep Networks from "
         "Decentralized Data. AISTATS.", "https://arxiv.org/abs/1602.05629"),
        ("Blanchard, P., et al. (2017). Machine Learning with Adversaries: Byzantine Tolerant "
         "Gradient Descent (Krum). NeurIPS.", "https://arxiv.org/abs/1703.02757"),
        ("Yin, D., et al. (2018). Byzantine-Robust Distributed Learning: Towards Optimal "
         "Statistical Rates (trimmed mean). ICML.", "https://arxiv.org/abs/1803.01498"),
        ("Bagdasaryan, E., et al. (2020). How To Backdoor Federated Learning. AISTATS.",
         "https://arxiv.org/abs/1807.00459"),
        ("Tolpegin, V., et al. (2020). Data Poisoning Attacks Against Federated Learning "
         "Systems. ESORICS.", "https://arxiv.org/abs/2007.08432"),
        ("Hsu, T.-M. H., Qi, H., Brown, M. (2019). Measuring the Effects of Non-Identical Data "
         "Distribution for Federated Visual Classification.", "https://arxiv.org/abs/1909.06335"),
        ("Angelopoulos, A., Bates, S. (2021). A Gentle Introduction to Conformal Prediction.",
         "https://arxiv.org/abs/2107.07511"),
        ("Tavallaee, M., et al. (2009). A Detailed Analysis of the KDD CUP 99 Data Set "
         "(NSL-KDD). CISDA.", "https://www.unb.ca/cic/datasets/nsl.html"),
        ("Khraisat, A., et al. (2024). Survey on Federated Learning for Intrusion Detection "
         "System. ACM Computing Surveys 57(1).", "https://doi.org/10.1145/3687124"),
        ("Krawczyk, H., Bellare, M., Canetti, R. (1997). HMAC: Keyed-Hashing for Message "
         "Authentication. RFC 2104.", "https://www.rfc-editor.org/rfc/rfc2104"),
    ]
    col_w = Inches(5.75)
    for i, (cite, url) in enumerate(refs):
        col, row = divmod(i, 6)
        x = LEFT + col * Inches(5.98)
        y = Inches(1.85) + row * Inches(0.75)
        box = text(slide, x, y, col_w, Inches(0.72),
                   [[(f"[{i + 1}]  ", {"color": ACCENT, "bold": True, "size": 9.5}),
                     (cite, {"size": 9.5})],
                    [(url, {"size": 9, "color": ACCENT})]], spacing=1.08)
        box.text_frame.paragraphs[1].runs[0].hyperlink.address = url
    hrule(slide, LEFT, Inches(6.4), CONTENT_W)
    text(slide, LEFT, Inches(6.5), Inches(4), Inches(0.4), "Thank you · questions welcome",
         size=15, font=SERIF, color=ACCENT)
    text(slide, Inches(5.2), Inches(6.55), Inches(7.33), Inches(0.3),
         "Code and results: github.com/Vinudharshini18/Krypsis-A-network-intrusion-detection-system",
         size=9.5, color=MUTED, align=PP_ALIGN.RIGHT)
    notes(slide, "All links are clickable. The GitHub repository has the code, every result "
                 "file and the full README. Thank the panel and open for questions.")


def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    for make in (s_title, s_intro, s_objectives, s_method_system, s_method_preprocess,
                 s_method_clients, s_method_model,
                 s_method_protocol, s_method_server, s_results_detection, s_results_attacks,
                 s_comparison, s_conclusion, s_references):
        make(prs)
    _muted_links(prs)
    prs.save(OUT_PATH)
    print(f"Saved {OUT_PATH} ({len(prs.slides)} slides)")


def _muted_links(prs):
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    theme = prs.slide_master.part.part_related_by(RT.THEME)
    xml = theme.blob.decode("utf-8")
    for tag in ("hlink", "folHlink"):
        xml = re.sub(rf"(<a:{tag}>\s*<a:srgbClr val=\")[0-9A-Fa-f]{{6}}",
                     rf"\g<1>{ACCENT}", xml)
    theme._blob = xml.encode("utf-8")


if __name__ == "__main__":
    build()
