"""
Builds Krypsis_Final_Review.pptx — the 14-slide final-review deck.

Dark "code editor" theme. The methodology is the core of the deck: an
overview of the eight steps, then one slide per step with the real code
from src/ (line-numbered) and a line-by-line explanation beside it.
Results, comparison and conclusion follow. Every slide has speaker notes.

Numbers are read from results/*.json, so the deck matches the experiments.

Run: ..\\venv\\Scripts\\python.exe build_final_review.py
"""

import json
import math
import os
import re
import textwrap

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(os.path.dirname(HERE), "results")
OUT_PATH = os.path.join(HERE, "Krypsis_Final_Review.pptx")
TOTAL = 14

# ------------------------------------------------------------------ theme

BG = RGBColor(0x0F, 0x16, 0x26)
PANEL = RGBColor(0x17, 0x22, 0x38)
PANEL_2 = RGBColor(0x1E, 0x2B, 0x46)
CODE_BG = RGBColor(0x0B, 0x11, 0x1E)
LINE = RGBColor(0x2A, 0x39, 0x58)
TEXT = RGBColor(0xE8, 0xED, 0xF5)
SOFT = RGBColor(0xA9, 0xB6, 0xCB)
MUTED = RGBColor(0x6E, 0x7F, 0x9C)
ACCENT = RGBColor(0x5E, 0xEA, 0xD4)
ACCENT_DIM = RGBColor(0x16, 0x3F, 0x45)
AMBER = RGBColor(0xFB, 0xBF, 0x24)
AMBER_DIM = RGBColor(0x45, 0x37, 0x16)
CORAL = RGBColor(0xF8, 0x71, 0x71)
# syntax colours
KW = RGBColor(0xC7, 0x92, 0xEA)
STR = RGBColor(0xA5, 0xD6, 0xA7)
NUM = RGBColor(0xF9, 0xA6, 0x6C)
FN = RGBColor(0x82, 0xAA, 0xFF)

HEAD = "Bahnschrift"
BODY = "Segoe UI"
MONO = "Consolas"

W, H = Inches(13.333), Inches(7.5)
LEFT = Inches(0.55)
CONTENT_W = Inches(12.23)

_no = [0]


def load(name):
    with open(os.path.join(RESULTS, name)) as f:
        return json.load(f)


CENTRAL = load("centralized_baseline.json")
FED_IID = load("federated_iid.json")[-1]
FED_ROUTER = load("federated_router.json")[-1]
MC = load("multiclass.json")
DEF = load("defense_experiment.json")["summary"]
PROT = load("protocol_experiment.json")
PG = PROT["summary"]
COMM = PROT["communication"]
FL, NL, NB = DEF["flnet/label_flip"], DEF["nslkdd/label_flip"], DEF["nslkdd/backdoor"]

# FLNET2023 training data: attack % per router (src/preprocess.py output).
ROUTER_ATTACK = [55.7, 83.2, 19.0, 92.1, 76.3, 66.1, 42.2, 50.8, 72.3, 68.5]


def p(x, d=1):
    return f"{100 * x:.{d}f}%"


# ------------------------------------------------------------------ primitives

def _e(*v):
    return [Emu(int(round(x))) for x in v]


def text(slide, x, y, w, h, content, size=14, color=TEXT, bold=False, font=BODY,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.15, italic=False,
         exact=None):
    """content: str ('\\n' = new paragraph) or list of paragraphs, each a list
    of (text, style) runs. exact: fixed line spacing in points."""
    box = slide.shapes.add_textbox(*_e(x, y, w, h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    paras = content.split("\n") if isinstance(content, str) else content
    for i, para in enumerate(paras):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.alignment = align
        par.line_spacing = Pt(exact) if exact else spacing
        runs = [(para, {})] if isinstance(para, str) else para
        for t, st in runs:
            r = par.add_run()
            r.text = t
            f = r.font
            f.size = Pt(st.get("size", size))
            f.color.rgb = st.get("color", color)
            f.bold = st.get("bold", bold)
            f.italic = st.get("italic", italic)
            f.name = st.get("font", font)
    return box


def rect(slide, x, y, w, h, fill=PANEL, line=None, radius=None, line_w=1.0, shape=None):
    kind = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE)
    s = slide.shapes.add_shape(kind, *_e(x, y, w, h))
    if radius and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.shadow.inherit = False
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(line_w)
    return s


def _plain(c):
    st = c._element.find(qn("p:style"))
    if st is not None:
        c._element.remove(st)
    return c


def line(slide, x1, y1, x2, y2, color=LINE, weight=1.25, head=False):
    c = _plain(slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, *_e(x1, y1, x2, y2)))
    c.line.color.rgb = color
    c.line.width = Pt(weight)
    if head:
        ln = c.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def pill(slide, x, y, w, h, label, fill=ACCENT_DIM, color=ACCENT, size=10.5, font=MONO):
    rect(slide, x, y, w, h, fill=fill, radius=0.5)
    text(slide, x, y, w, h, label, size=size, color=color, bold=True, font=font,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def notes(slide, content):
    slide.notes_slide.notes_text_frame.text = textwrap.dedent(content).strip()


def base(prs, tag=None, title=None, subtitle=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _no[0] += 1
    rect(slide, 0, 0, W, H, fill=BG)
    if title:
        text(slide, LEFT, Inches(0.38), Inches(9), Inches(0.3), tag.upper(), size=12,
             bold=True, color=ACCENT, font=HEAD)
        text(slide, LEFT, Inches(0.62), CONTENT_W, Inches(0.62), title, size=30, font=HEAD)
        if subtitle:
            text(slide, LEFT, Inches(1.2), CONTENT_W, Inches(0.4), subtitle, size=14,
                 color=SOFT)
    text(slide, LEFT, Inches(7.02), Inches(6), Inches(0.3), "KRYPSIS  ·  FINAL REVIEW",
         size=10, color=MUTED, font=HEAD)
    text(slide, Inches(11.28), Inches(7.02), Inches(1.5), Inches(0.3),
         f"{_no[0]:02d} / {TOTAL}", size=10, color=MUTED, font=HEAD, align=PP_ALIGN.RIGHT)
    return slide


# ------------------------------------------------------------------ code panel

KEYWORDS = {"def", "return", "for", "in", "if", "not", "or", "and", "class", "else",
            "None", "True", "False", "import", "from", "with", "as", "is", "lambda"}
_TOKEN = re.compile(r'(#.*$)|("[^"]*")|(\b\d+(?:\.\d+)?(?:e-?\d+)?\b)|([A-Za-z_]\w*)|(.)')


def _code_runs(src_line):
    runs, prev = [], None
    for m in _TOKEN.finditer(src_line):
        comment, string, number, word, _ = m.groups()
        if comment:
            runs.append((comment, {"color": MUTED, "italic": True}))
        elif string:
            runs.append((string, {"color": STR}))
        elif number:
            runs.append((number, {"color": NUM}))
        elif word in KEYWORDS:
            runs.append((word, {"color": KW}))
        elif word and prev in ("def", "class"):
            runs.append((word, {"color": FN}))
        else:
            runs.append((m.group(0), {}))
        if word or comment or string or number:
            prev = word
    return runs or [(" ", {})]


CODE_SIZE = 12.5
CODE_LEADING = 16.5


def code_panel(slide, source, filename, x=LEFT, y=Inches(1.75), w=Inches(8.0),
               h=Inches(5.12)):
    lines = textwrap.dedent(source).strip("\n").split("\n")
    assert max(len(s) for s in lines) <= 70, max(lines, key=len)
    # Shrink the type a little when a snippet is long, so it always fits.
    leading = min(CODE_LEADING, (h - Inches(0.75)) / 914400 * 72 / len(lines))
    size = min(CODE_SIZE, leading / 1.32)
    rect(slide, x, y, w, h, fill=CODE_BG, line=LINE, radius=0.025)
    rect(slide, x, y, w, Inches(0.42), fill=PANEL_2, radius=None)
    for i, c in enumerate((CORAL, AMBER, ACCENT)):
        rect(slide, x + Inches(0.2) + i * Inches(0.2), y + Inches(0.15), Inches(0.12),
             Inches(0.12), fill=c, shape=MSO_SHAPE.OVAL)
    text(slide, x + Inches(0.95), y, w - Inches(1.1), Inches(0.42), filename, size=11,
         color=SOFT, font=MONO, anchor=MSO_ANCHOR.MIDDLE)
    top = y + Inches(0.6)
    text(slide, x + Inches(0.12), top, Inches(0.4), h - Inches(0.7),
         [[(str(i + 1), {})] for i in range(len(lines))], size=size - 1.5, color=MUTED,
         font=MONO, align=PP_ALIGN.RIGHT, exact=leading)
    line(slide, x + Inches(0.62), top - Inches(0.05), x + Inches(0.62), y + h - Inches(0.15),
         color=LINE, weight=0.75)
    text(slide, x + Inches(0.78), top, w - Inches(0.9), h - Inches(0.7),
         [_code_runs(s) for s in lines], size=size, font=MONO, exact=leading)


def explain(slide, items, x=Inches(8.8), y=Inches(1.75), w=Inches(3.98), gap=Inches(0.08),
            heading="HOW IT WORKS"):
    """items: (line tag, heading, body). Returns the y below the last item."""
    if heading:
        text(slide, x, y, w, Inches(0.3), heading, size=11, bold=True, color=MUTED, font=HEAD)
        y += Inches(0.4)
    for tag, head, body in items:
        pill(slide, x, y + Inches(0.02), Inches(0.82), Inches(0.28), tag)
        lines_ = 1 + math.ceil(len(body) / 46)
        h = Inches(0.3 + 0.2 * lines_)
        text(slide, x + Inches(0.95), y, w - Inches(0.95), h,
             [[(head, {"bold": True, "size": 13, "font": HEAD})],
              [(body, {"size": 11.5, "color": SOFT})]], spacing=1.1)
        y += h + gap
    return y


def method_slide(prs, step, title, subtitle, filename, source, items, note, extra=None):
    slide = base(prs, f"Methodology  ·  step {step} of 8", title, subtitle)
    code_panel(slide, source, filename)
    end = explain(slide, items)
    if extra:
        extra(slide, end)
    notes(slide, note)
    return slide


def callout(slide, y, content, color=AMBER, fill=AMBER_DIM, x=Inches(8.8), w=Inches(3.98),
            h=Inches(0.8)):
    rect(slide, x, y, w, h, fill=fill, radius=0.08)
    rect(slide, x, y, Inches(0.06), h, fill=color)
    text(slide, x + Inches(0.2), y, w - Inches(0.3), h, content, size=11.5, color=TEXT,
         anchor=MSO_ANCHOR.MIDDLE, spacing=1.1)


# ------------------------------------------------------------------ charts

def bar_chart(slide, x, y, w, h, categories, series, colors, title=None, fmt='0.0"%"',
              vmin=0, vmax=None, unit=None):
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values)
    chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, *_e(x, y, w, h), data).chart
    chart.font.size = Pt(11)
    chart.font.name = BODY
    chart.font.color.rgb = SOFT
    chart.has_title = bool(title)
    if title:
        chart.chart_title.text_frame.text = title
        r = chart.chart_title.text_frame.paragraphs[0].runs[0]
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(13), True, TEXT, HEAD
    plot = chart.plots[0]
    plot.gap_width, plot.overlap = 70, -8
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format, dl.number_format_is_linked = fmt, False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size, dl.font.color.rgb = Pt(11), TEXT
    for s, c in zip(plot.series, colors):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = c
    va = chart.value_axis
    va.minimum_scale = vmin
    if vmax is not None:
        va.maximum_scale = vmax
    if unit:
        va.major_unit = unit
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = LINE
    va.format.line.fill.background()
    va.tick_labels.number_format = '0"%"'
    va.tick_labels.number_format_is_linked = False
    va.tick_labels.font.color.rgb = MUTED
    ca = chart.category_axis
    ca.format.line.color.rgb = LINE
    ca.tick_labels.font.color.rgb = SOFT
    chart.has_legend = len(series) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.color.rgb = SOFT
    return chart


def mini_bars(slide, x, y, w, h, values, labels, color=ACCENT):
    """Small hand-drawn bar strip (values in %)."""
    n = len(values)
    step = w / n
    bw = step * 0.62
    base_y = y + h - Inches(0.22)
    max_h = h - Inches(0.5)
    for i, (v, lab) in enumerate(zip(values, labels)):
        bx = x + i * step + (step - bw) / 2
        bh = max_h * v / 100
        rect(slide, bx, base_y - bh, bw, bh, fill=color)
        text(slide, bx - Inches(0.1), base_y - bh - Inches(0.22), bw + Inches(0.2),
             Inches(0.2), f"{v:.0f}", size=9, color=SOFT, align=PP_ALIGN.CENTER)
        text(slide, bx - Inches(0.1), base_y + Inches(0.03), bw + Inches(0.2), Inches(0.2),
             lab, size=9, color=MUTED, align=PP_ALIGN.CENTER)
    line(slide, x, base_y, x + w, base_y, color=LINE)


# ------------------------------------------------------------------ slides

def s01_title(prs):
    slide = base(prs)
    text(slide, LEFT + Inches(0.1), Inches(0.9), Inches(7), Inches(0.3),
         "COMPUTER NETWORKS  ·  FINAL PROJECT REVIEW", size=12, bold=True, color=ACCENT,
         font=HEAD)
    text(slide, LEFT + Inches(0.1), Inches(1.4), Inches(7.5), Inches(1.4), "KRYPSIS", size=80,
         font=HEAD, color=TEXT)
    text(slide, LEFT + Inches(0.1), Inches(2.85), Inches(7.0), Inches(1.0),
         "Federated network intrusion detection with a\nsecurity-fused model-update protocol",
         size=20, color=SOFT, spacing=1.2)
    chips = ["FLNET2023 · 10 routers", "FedAvg", "HMAC + fingerprint", "Global vs Mondrian"]
    cx = LEFT + Inches(0.1)
    for c in chips:
        w = Inches(0.3 + 0.08 * len(c))
        pill(slide, cx, Inches(4.05), w, Inches(0.36), c, size=10.5, font=BODY)
        cx += w + Inches(0.12)
    line(slide, LEFT + Inches(0.1), Inches(4.85), LEFT + Inches(7.0), Inches(4.85))
    team = [("Rithika K", "CB.SC.U4AIE25126"), ("Pradhaniya S", "CB.SC.U4AIE25148"),
            ("Sathya K", "CB.SC.U4AIE25154"), ("Vinudharshini PP", "CB.SC.U4AIE25161")]
    for i, (name, roll) in enumerate(team):
        col, row = i % 2, i // 2
        text(slide, LEFT + Inches(0.1) + col * Inches(3.5), Inches(5.1) + row * Inches(0.8),
             Inches(3.3), Inches(0.75),
             [[(name, {"bold": True, "size": 15, "font": HEAD})],
              [(roll, {"size": 11, "color": MUTED, "font": MONO})]], spacing=1.1)

    # Network graphic: one server, ten routers.
    cx, cy, r = Inches(10.6), Inches(3.55), Inches(2.2)
    nodes = []
    for i in range(10):
        a = -math.pi / 2 + 2 * math.pi * i / 10
        nodes.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    for nx, ny in nodes:
        line(slide, cx, cy, nx, ny, color=LINE, weight=1)
    for i, (nx, ny) in enumerate(nodes):
        d = Inches(0.5)
        rect(slide, nx - d / 2, ny - d / 2, d, d, fill=PANEL_2, line=ACCENT, line_w=1.25,
             shape=MSO_SHAPE.OVAL)
        text(slide, nx - d / 2, ny - d / 2, d, d, f"R{i + 1}", size=10, color=TEXT,
             font=HEAD, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    d = Inches(1.15)
    rect(slide, cx - d / 2, cy - d / 2, d, d, fill=ACCENT_DIM, line=ACCENT, line_w=2,
         shape=MSO_SHAPE.OVAL)
    text(slide, cx - d / 2, cy - d / 2, d, d, "Server", size=13, bold=True, color=ACCENT,
         font=HEAD, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    notes(slide, """
        Good morning. Our project is Krypsis: a network intrusion detection system trained
        with federated learning across 10 routers, protected by our own update protocol.
        The picture on the right is the setup: ten routers, each keeping its own traffic,
        and one server that combines their model updates.
        Most of this talk is the methodology, step by step, with the real code we wrote.
    """)


def s02_problem(prs):
    slide = base(prs, "Introduction  ·  objectives",
                 "The problem, and what we set out to do")
    rect(slide, LEFT, Inches(1.5), Inches(5.85), Inches(3.95), fill=PANEL, radius=0.04)
    text(slide, LEFT + Inches(0.3), Inches(1.7), Inches(5), Inches(0.3), "THE PROBLEM",
         size=11, bold=True, color=MUTED, font=HEAD)
    probs = [
        ("Detection needs data", "An intrusion detector learns from traffic, but traffic "
         "logs are private and cannot be pooled."),
        ("Federated learning helps", "Each router trains locally; only model updates "
         "travel to the server (FedAvg)."),
        ("Updates become the risk", "Updates can be tampered with on the way, or poisoned "
         "by a bad client."),
    ]
    for i, (h_, b) in enumerate(probs):
        y = Inches(2.15) + i * Inches(1.07)
        text(slide, LEFT + Inches(0.3), y, Inches(0.5), Inches(0.5), f"0{i + 1}", size=20,
             color=ACCENT, font=HEAD)
        text(slide, LEFT + Inches(0.9), y, Inches(4.75), Inches(1.0),
             [[(h_, {"bold": True, "size": 14, "font": HEAD})],
              [(b, {"size": 12, "color": SOFT})]], spacing=1.1)

    x = Inches(6.65)
    text(slide, x, Inches(1.7), Inches(5.5), Inches(0.3), "OBJECTIVES", size=11, bold=True,
         color=MUTED, font=HEAD)
    objs = ["Detect attacks without sharing raw traffic",
            "Design our own secure update protocol",
            "Stop tampered and poisoned updates before averaging",
            "Keep the protocol's message overhead small",
            "Test global vs per-cluster (Mondrian) thresholds"]
    for i, o in enumerate(objs):
        y = Inches(2.1) + i * Inches(0.66)
        rect(slide, x, y, Inches(5.98), Inches(0.54), fill=PANEL, radius=0.15)
        text(slide, x + Inches(0.2), y, Inches(0.4), Inches(0.54), "✓", size=14, bold=True,
             color=ACCENT, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, x + Inches(0.6), y, Inches(5.3), Inches(0.54), o, size=13.5,
             anchor=MSO_ANCHOR.MIDDLE)
    rect(slide, LEFT, Inches(5.7), CONTENT_W, Inches(1.05), fill=ACCENT_DIM, radius=0.08)
    text(slide, LEFT + Inches(0.3), Inches(5.7), CONTENT_W - Inches(0.6), Inches(1.05), [
        [("RESEARCH QUESTION   ", {"bold": True, "color": ACCENT, "size": 12, "font": HEAD}),
         ("Routers see different traffic (non-IID). Does one global anomaly threshold wrongly "
          "flag honest but unusual routers, and do per-cluster (Mondrian) thresholds fix it?",
          {"size": 14})]], anchor=MSO_ANCHOR.MIDDLE, spacing=1.2)
    notes(slide, """
        An intrusion detector needs lots of varied traffic to learn, but organisations
        cannot share their traffic because it is private. Federated learning solves that:
        each router trains locally and only sends model updates. But then the updates
        become the weak point: they can be changed on the way, or a bad client can send a
        poisoned one.
        Our five objectives are on the right. The research question at the bottom: since
        every router sees different traffic, does a single global threshold wrongly flag
        honest routers, and does a per-cluster Mondrian threshold do better?
    """)


def s03_overview(prs):
    slide = base(prs, "Methodology  ·  overview",
                 "Eight steps, from raw traffic to a protected global model",
                 "Each step is one of the next slides, with the code that implements it.")
    steps = [
        ("01", "Data & preprocessing", "preprocess.py"),
        ("02", "Client split", "client_simulation.py"),
        ("03", "Model", "model.py"),
        ("04", "Federated training", "federated_training.py"),
        ("05", "Krypsis message", "protocol.py · pack"),
        ("06", "Server verification", "protocol.py · unpack"),
        ("07", "Anomaly scoring", "protocol.py · AnomalyScorer"),
        ("08", "Threshold & aggregation", "calibrators · second check"),
    ]
    bw, bh, gap = Inches(2.7), Inches(1.55), Inches(0.48)
    for i, (num, name, src) in enumerate(steps):
        row, col = divmod(i, 4)
        if row == 1:
            col = 3 - col          # second row runs right to left
        x = LEFT + col * (bw + gap)
        y = Inches(1.95) + row * Inches(2.35)
        ours = i >= 4
        rect(slide, x, y, bw, bh, fill=ACCENT_DIM if ours else PANEL,
             line=ACCENT if ours else LINE, radius=0.07)
        text(slide, x + Inches(0.22), y + Inches(0.18), Inches(1), Inches(0.4), num, size=22,
             color=ACCENT, font=HEAD)
        text(slide, x + Inches(0.22), y + Inches(0.68), bw - Inches(0.4), Inches(0.85),
             [[(name, {"bold": True, "size": 15, "font": HEAD})],
              [(src, {"size": 10.5, "color": SOFT, "font": MONO})]], spacing=1.15)
        if i in (0, 1, 2):
            line(slide, x + bw, y + bh / 2, x + bw + gap, y + bh / 2, color=MUTED, head=True)
        if i == 3:
            line(slide, x + bw / 2, y + bh, x + bw / 2, y + Inches(2.35), color=MUTED,
                 head=True)
        if i in (4, 5, 6):
            line(slide, x, y + bh / 2, x - gap, y + bh / 2, color=MUTED, head=True)
    text(slide, LEFT, Inches(5.95), Inches(9), Inches(0.35), [
        [("■ ", {"color": ACCENT}), ("Steps 05–08 are our protocol, Krypsis.  ", {}),
         ("Steps 04–08 repeat every round: 12–15 rounds per run.", {"color": SOFT})]],
        size=12.5)
    text(slide, LEFT, Inches(6.35), CONTENT_W, Inches(0.5),
         "One round: routers train locally → each sends a signed, fingerprinted update → "
         "the server verifies, scores and filters → capped FedAvg → new global model.",
         size=12, color=MUTED)
    notes(slide, """
        This is the whole method in eight steps. The top row is the federated learning
        system: prepare the data, split it into clients, define the model, train it with
        FedAvg. The highlighted bottom row is our protocol, Krypsis: build the message,
        verify it on the server, score how suspicious it is, then decide with a threshold
        and aggregate. Steps four to eight repeat every round. The next eight slides go
        through each step with its code.
    """)


def s04_data(prs):
    method_slide(prs, 1, "Data and preprocessing",
                 "FLNET2023: 10 routers, 11 traffic types  →  564,007 train / 79,491 test "
                 "flows, 66 features.",
                 "src/preprocess.py  (excerpt)", '''
        SAMPLE_FRACTION = 0.10       # 4.8 M flows -> 10% of each file
        MIN_ROWS_PER_FILE = 2000     # keeps small attack files visible
        DROP_COLUMNS = ["src_ip", "dst_ip", "src_port", "timestamp"]

        df["router"] = int(match.group(1))     # Dataset-3.csv -> router 3

        features = features.replace([np.inf, -np.inf], np.nan)
        bad = features.isna().any(axis=1)
        df = df.loc[~bad]                      # drop broken rows
        constant = [c for c in cols if train_df[c].nunique() <= 1]

        def signed_log1p(x):                   # values span 1 to 1e9
            return np.sign(x) * np.log1p(np.abs(x))

        y = (~df["label"].str.lower().isin(NORMAL_LABELS)).astype(int)
        scaler = MinMaxScaler()                # fitted on TRAIN only
        X_train = scaler.fit_transform(signed_log1p(X_train_raw))
        X_test = np.clip(scaler.transform(signed_log1p(X_test_raw)), 0, 1)
    ''', [
        ("L1–2", "Sample", "10% of every file, at least 2,000 rows, so training many runs "
                           "stays fast."),
        ("L3", "Drop identifiers", "IPs, port and time removed: learn behaviour, not "
                                   "the attacker's address."),
        ("L5", "Tag the router", "The router number becomes the client ID in step 2."),
        ("L7–10", "Clean", "inf / NaN rows and 12 constant columns removed."),
        ("L12–18", "Label and scale", "Normal = 0, attack = 1. Log, then 0–1 scaling "
                                      "fitted on training data only."),
    ], """
        Step one is the data. FLNET2023 records traffic at 10 routers, with normal traffic
        and 10 attack types. Line 1 and 2: we sample 10 percent of each file, because the
        full 4.8 million flows is too much to train many times. Line 3: we drop IP
        addresses, port and timestamp, otherwise the model would learn the attacker's
        address instead of what an attack looks like. Line 5: every flow keeps its router
        number, which becomes its client in step two. Lines 7 to 10 remove broken rows and
        columns that never change. Lines 12 to 18: the label is 0 for normal and 1 for
        attack; values are log-scaled then scaled to 0 to 1, with the scaler fitted only on
        training data so the test set stays unseen. The result: 564,007 training flows,
        79,491 test flows, 66 features.
    """)


def s05_clients(prs):
    def extra(slide, y):
        text(slide, Inches(8.8), Inches(5.55), Inches(3.98), Inches(0.3),
             "FLNET2023 · attack % per router", size=10.5, color=MUTED, font=HEAD)
        mini_bars(slide, Inches(8.8), Inches(5.8), Inches(3.98), Inches(1.1), ROUTER_ATTACK,
                  [str(i) for i in range(1, 11)])

    method_slide(prs, 2, "Client split: IID vs non-IID",
                 "IID = every client gets a similar mix.  Non-IID = every client is different.",
                 "src/client_simulation.py · src/preprocess_nslkdd.py", '''
        def split_by_router(router):           # FLNET2023: real non-IID
            routers = np.unique(router)
            return np.searchsorted(routers, router)   # router 1..10 -> 0..9

        def split_iid(num_samples, num_clients, seed=42):   # control
            rng = np.random.default_rng(seed)
            indices = rng.permutation(num_samples)
            chunks = np.array_split(indices, num_clients)
            ...                                # chunk k -> client k

        def split_non_iid_dirichlet(labels, num_clients, alpha, seed):
            rng = np.random.default_rng(seed)  # NSL-KDD, alpha = 0.5
            assignment = np.full(len(labels), -1, dtype=int)
            for category in np.unique(labels):
                idx = np.where(labels == category)[0]
                rng.shuffle(idx)
                share = rng.dirichlet(alpha * np.ones(num_clients))
                sizes = (share * len(idx)).astype(int)
                ...                            # give idx to clients by sizes
            return assignment
    ''', [
        ("L1–3", "Router split", "Each real router is one client: the data is naturally "
                                 "uneven."),
        ("L5–9", "IID split", "Shuffle and deal evenly: a control to measure the cost of "
                              "unevenness."),
        ("L11–20", "Dirichlet split", "Each attack type is shared out with random "
                                      "proportions; smaller alpha = more uneven."),
    ], """
        Step two decides which data each client holds. Lines 1 to 3: for FLNET2023 each real
        router is one client, so the data is naturally uneven: router 3 has 19 percent
        attacks, router 4 has 92 percent, as the small chart shows. Lines 5 to 9: the IID
        split shuffles everything and deals it out evenly. It is our control. Lines 11 to
        20: for NSL-KDD we create uneven clients with a Dirichlet split. For every attack
        type, the Dirichlet distribution gives each of the 10 clients a random share. Alpha
        0.5 makes them quite uneven. Uneven data matters because an honest client with
        unusual data can look like an attacker.
    """, extra)


def s06_model(prs):
    def extra(slide, y):
        layers_ = ["66", "256", "128", "64", "1"]
        x0, yy = Inches(8.8), Inches(5.75)
        bw, gap = Inches(0.62), Inches(0.22)
        for i, n in enumerate(layers_):
            x = x0 + i * (bw + gap)
            rect(slide, x, yy, bw, Inches(0.5), fill=ACCENT_DIM if 0 < i < 4 else PANEL,
                 line=ACCENT if 0 < i < 4 else LINE, radius=0.15)
            text(slide, x, yy, bw, Inches(0.5), n, size=12, bold=True, font=HEAD,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
            if i < 4:
                line(slide, x + bw, yy + Inches(0.25), x + bw + gap, yy + Inches(0.25),
                     color=MUTED, head=True)
        text(slide, x0, yy + Inches(0.6), Inches(3.98), Inches(0.5),
             "input → hidden layers → output · 58,369 weights", size=10.5, color=MUTED)

    method_slide(prs, 3, "Model: a multilayer perceptron",
                 "The same model is used centrally (baseline) and on every client.",
                 "src/model.py", '''
        layers = tf.keras.layers

        def build_model(input_dim):            # input_dim = 66 features
            l2 = tf.keras.regularizers.l2(1e-4)
            model = tf.keras.Sequential([
                layers.Input(shape=(input_dim,)),
                layers.Dense(256, activation="relu", kernel_regularizer=l2),
                layers.Dropout(0.3),
                layers.Dense(128, activation="relu", kernel_regularizer=l2),
                layers.Dropout(0.3),
                layers.Dense(64, activation="relu", kernel_regularizer=l2),
                layers.Dropout(0.2),
                layers.Dense(1, activation="sigmoid"),
            ])
            model.compile(optimizer="adam", loss="binary_crossentropy",
                          metrics=["accuracy"])
            return model
    ''', [
        ("L7–13", "Three hidden layers", "256, 128 and 64 neurons with ReLU learn patterns "
                                         "in the flow features."),
        ("L8–12", "Dropout + L2", "Randomly switch off neurons and keep weights small, "
                                  "to avoid memorising."),
        ("L13", "Sigmoid output", "One number from 0 to 1: the chance that a flow is an "
                                  "attack."),
        ("L15", "Training", "Adam optimiser, binary cross-entropy loss."),
    ], """
        Step three is the model, a multilayer perceptron. It takes the 66 features. Lines 7
        to 13 are three hidden layers of 256, 128 and 64 neurons. Lines 8, 10 and 12 add
        dropout, which switches off random neurons during training, and line 4 adds L2,
        which keeps the weights small. Both stop the model from memorising. Line 13: one
        sigmoid output, the probability that a flow is an attack. It has 58,369 weights,
        which is exactly what every client sends to the server each round. Trained on all
        data in one place, this model is our centralized baseline.
    """, extra)


def s07_fedavg(prs):
    def extra(slide, y):
        callout(slide, Inches(6.0),
                [[("Result  ", {"bold": True, "color": AMBER}),
                  (f"FedAvg over 10 routers {p(FED_ROUTER['accuracy'], 2)} vs "
                   f"centralized {p(CENTRAL['accuracy'])}.", {})]])

    method_slide(prs, 4, "Federated training with FedAvg",
                 "Clients train locally; the server averages their weights, weighted by data "
                 "size.", "src/federated_training.py", '''
        def federated_average(weight_list, sample_counts):
            total = sum(sample_counts)
            averaged = []
            for layer_idx in range(len(weight_list[0])):
                layer_sum = sum(weight_list[i][layer_idx]
                                * (sample_counts[i] / total)
                                for i in range(len(weight_list)))
                averaged.append(layer_sum)
            return averaged

        for round_num in range(1, num_rounds + 1):        # 15 rounds
            for client_id in range(num_clients):          # 10 routers
                mask = assignment == client_id
                local_model.set_weights(global_weights)
                local_model.fit(X_train[mask], y_train[mask], epochs=2)
                local_weights.append(local_model.get_weights())
                sample_counts.append(mask.sum())
            global_weights = federated_average(local_weights, sample_counts)
            metrics = evaluate(global_model, X_test, y_test)
    ''', [
        ("L14", "Start from global", "Every client copies the current global model."),
        ("L15", "Train locally", "2 passes over its own data only; raw traffic never "
                                 "leaves."),
        ("L16–17", "Send back", "Its new weights and how many samples it used."),
        ("L1–9", "Weighted average", "Each layer averaged; a client with more data counts "
                                     "more."),
    ], """
        Step four is federated training. Read the loop at the bottom first. Every round,
        line 14: each client copies the global model. Line 15: it trains on its own data for
        two passes. Lines 16 and 17: it sends back its new weights and its number of
        samples. Then lines 1 to 9, FedAvg: for every layer, the server multiplies each
        client's weights by that client's share of the data and adds them up. Line 18 makes
        that the new global model, and line 19 tests it. After 15 rounds the federated model
        reaches 99.93 percent, almost the same as the centralized model. In the protocol
        runs, steps five to eight sit between training and averaging.
    """, extra)


def s08_message(prs):
    def extra(slide, y):
        parts = [("4 B", "length", PANEL), ("~1.5 KB", "header + fingerprint", ACCENT_DIM),
                 (f"{COMM['raw_payload_bytes'] / 1000:.0f} KB", "model update", PANEL),
                 ("32 B", "HMAC tag", AMBER_DIM)]
        widths = [0.62, 1.2, 1.36, 0.68]
        x = Inches(8.8)
        for (num, lab, fill), wv in zip(parts, widths):
            w = Inches(wv)
            rect(slide, x, Inches(5.7), w, Inches(0.75), fill=fill, line=LINE)
            text(slide, x, Inches(5.72), w, Inches(0.72),
                 [[(num, {"bold": True, "size": 11.5, "font": HEAD})],
                  [(lab, {"size": 9, "color": SOFT})]], align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE, spacing=1.0)
            x += w + Inches(0.04)
        text(slide, Inches(8.8), Inches(6.52), Inches(3.98), Inches(0.35),
             f"+{p(COMM['krypsis_overhead_bytes'] / COMM['raw_payload_bytes'], 2)} size · "
             f"JSON would be {COMM['http_json_bytes'] / COMM['raw_payload_bytes']:.1f}×",
             size=11, color=AMBER)

    method_slide(prs, 5, "Krypsis message: fingerprint + integrity tag",
                 "Built on the client, right after local training, for every update.",
                 "src/protocol.py  (client side)", '''
        class Fingerprinter:
            def __init__(self, weight_shapes):
                rng = np.random.default_rng(SKETCH_SEED)      # public: 2023
                self.projection = (rng.standard_normal((SKETCH_DIM, self.dim))
                                   / math.sqrt(SKETCH_DIM)).astype(np.float32)

            def compute(self, delta):
                return {"l2": float(np.linalg.norm(delta)),
                        "layer_l2": [float(np.linalg.norm(delta[s]))
                                     for s in self.layer_slices],
                        "sketch": (self.projection @ delta).tolist()}

        def pack(client_id, round_num, num_samples, delta, key, fp):
            header = json.dumps({"client": client_id, "round": round_num,
                                 "n": num_samples, "fp": fp.compute(delta)},
                                separators=(",", ":")).encode()
            payload = delta.astype(np.float32).tobytes()
            tag = hmac.new(key, header + payload, hashlib.sha256).digest()
            return len(header).to_bytes(4, "big") + header + payload + tag
    ''', [
        ("L3–5", "Shared random projection", "Public seed, so client and server compute "
                                             "the same sketch."),
        ("L7–11", "Fingerprint", "Update size, size per layer, and 64 numbers that "
                                 "capture its direction."),
        ("L17–19", "Payload + tag", "Update as raw bytes, sealed with HMAC-SHA256 and the "
                                    "client's secret key."),
    ], """
        Step five is our protocol on the client side. Delta is the update: new weights minus
        global weights. Lines 7 to 11 compute its fingerprint: the overall size of the
        update, the size per layer, and a sketch, which is the update squeezed into 64
        numbers by a random projection. Lines 3 to 5 make that projection from a public seed,
        so the server can compute exactly the same sketch. Lines 13 to 16 put the client ID,
        round, sample count and fingerprint into a header. Line 17 adds the update as raw
        bytes. Line 18 is the integrity tag: an HMAC with the client's secret key over the
        header and payload. The whole message is only 0.67 percent bigger than the update
        itself; plain JSON would be 5.6 times bigger.
    """, extra)


def s09_verify(prs):
    def extra(slide, y):
        callout(slide, Inches(6.0),
                [[("Result  ", {"bold": True, "color": AMBER}),
                  (f"{PG['global']['tamper_rejected']} of {PG['global']['tamper_sent']} "
                   "tampered messages rejected (one byte flipped each).", {})]])

    method_slide(prs, 6, "Server verification: reject before reading",
                 "Two hard checks. Anything that fails is dropped before it can be averaged.",
                 "src/protocol.py · unpack  (excerpt)", '''
        def unpack(message, keys, fingerprinter):
            header_len = int.from_bytes(message[:4], "big")
            header_bytes = message[4:4 + header_len]
            payload = message[4 + header_len:-32]
            tag = message[-32:]
            header = json.loads(header_bytes)
            key = keys[header["client"]]
            expected = hmac.new(key, header_bytes + payload,
                                hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected):
                return header, None, "bad_tag"            # changed on the way
            delta = np.frombuffer(payload, dtype=np.float32)
            if delta.size != fingerprinter.dim:
                return header, None, "bad_size"
            actual = fingerprinter.compute(delta)       # recompute it
            claimed = header["fp"]
            if not np.allclose(actual["sketch"], claimed["sketch"], ...):
                return header, None, "fingerprint_mismatch"
            return header, delta, None
    ''', [
        ("L2–7", "Split the message", "Length, header, payload and tag; find the "
                                      "client's key."),
        ("L8–11", "Check the tag", "Recompute the HMAC. One changed byte gives a different "
                                   "tag: reject."),
        ("L15–18", "Check the fingerprint", "Recompute it from the payload, so a client "
                                            "cannot fake an innocent one."),
    ], """
        Step six runs on the server. Lines 2 to 7 split the message into its parts and look up
        the key of the client who sent it. Lines 8 to 11: the server makes the HMAC again with
        that key. If even one byte changed on the way, the tags differ and the message is
        rejected. Lines 12 to 14 check the size. Lines 15 to 18: the server does not trust the
        fingerprint in the header. It computes it again from the payload, and if it does not
        match, the message is rejected, so a cheating client cannot hide a bad update behind
        a nice fingerprint. In our tests we flipped one byte in 105 messages, and all 105 were
        rejected.
    """, extra)


def s10_scoring(prs):
    def extra(slide, y):
        callout(slide, Inches(6.0),
                [[("Why lines 15–21  ", {"bold": True, "color": AMBER}),
                  ("our first version used fixed limits and flagged 65–96% of honest "
                   "updates.", {})]])

    method_slide(prs, 7, "Anomaly scoring: three cheap scores",
                 "Computed from the fingerprints only, before touching the full update.",
                 "src/protocol.py · AnomalyScorer  (excerpt)", '''
        def score_round(self, fps):
            sketches = {c: np.asarray(f["sketch"]) for c, f in fps.items()}
            consensus = np.median(np.stack(list(sketches.values())), axis=0)
            median_norm = float(np.median([f["l2"] for f in fps.values()]))
            scores = {}
            for c, f in fps.items():
                prev = self.prev_sketch.get(c)
                scores[c] = {
                    "norm": abs(math.log(f["l2"] / median_norm)),
                    "consensus": 1.0 - cosine(sketches[c], consensus),
                    "history": 1.0 - cosine(sketches[c], prev),
                }
            return standardize(scores)

        def standardize(scores):               # robust z within the round
            for name in SCORE_NAMES:
                values = np.array([s[name] for s in scores.values()])
                median = float(np.median(values))
                scale = 1.4826 * float(np.median(np.abs(values - median)))
                for c in scores:
                    out[c][name] = (scores[c][name] - median) / scale
    ''', [
        ("L9", "Norm score", "Is this update much bigger or smaller than the others?"),
        ("L10", "Consensus score", "Does it point away from the median of all clients? "
                                   "Medians resist attackers."),
        ("L11", "History score", "Is it unlike this client's own last update?"),
        ("L15–21", "Standardize", "Compare each score with this round's other clients "
                                  "(robust z-score)."),
    ], """
        Step seven gives each update three cheap scores, using only the fingerprints. Line 3
        builds the consensus: the median sketch of all clients. We use the median because a
        few attackers cannot drag it. Line 9, the norm score: is this update much bigger or
        smaller than the others? Line 10, the consensus score: does it point in a different
        direction from everyone else? Line 11, the history score: is it different from this
        same client's last update? Lines 15 to 21 standardize each score within the round.
        This was a lesson: our first version used fixed limits, and once training settled,
        65 to 96 percent of honest updates were flagged. Comparing within the round fixed it.
    """, extra)


def s11_threshold(prs):
    def extra(slide, y):
        callout(slide, Inches(6.05),
                [[("Global ", {"bold": True, "color": ACCENT}),
                  ("one limit for everyone.  ", {}),
                  ("Mondrian ", {"bold": True, "color": ACCENT}),
                  ("one limit per cluster of similar clients.", {})]],
                color=ACCENT, fill=ACCENT_DIM)

    method_slide(prs, 8, "Threshold, second check and capped averaging",
                 "Rounds 1–5 are clean and set the limits; from round 6 every update is "
                 "judged.", "src/protocol.py · defense_experiment.py  (excerpt)", '''
        def conformal_threshold(scores, alpha):        # alpha = 0.05
            rank = math.ceil((len(scores) + 1) * (1 - alpha))
            return float(np.sort(scores)[rank - 1])

        # Global: one threshold per score for all clients
        # Mondrian: k-means (k = 3) on calibration sketches, one per cluster
        labels = KMeans(n_clusters=k, n_init=10).fit_predict(profiles)

        passed = {c: d for c, d in deltas.items()
                  if not is_flagged(scores[c], calibrator.threshold_for(c))}
        flagged = {c: d for c, d in deltas.items() if c not in passed}
        rescued = second_check(passed, flagged, 0.2)   # trimmed-mean test
        accepted = {**passed, **rescued}

        weights = capped_weights({c: counts[c] for c in accepted}, 1.5)
        global_vec = global_vec + sum(accepted[c] * weights[c]
                                      for c in accepted)
    ''', [
        ("L1–3", "Set the limit", "From clean rounds: only ~5% of honest scores should "
                                  "cross it."),
        ("L9–11", "Flag", "Any score above its limit flags the update."),
        ("L12–13", "Second check", "A flagged update close to a trimmed-mean reference is "
                                   "rescued."),
        ("L15–17", "Capped FedAvg", "No client gets more than 15% weight (1.5 × 1/10)."),
    ], """
        Step eight makes the decision. Lines 1 to 3: during the 5 clean calibration rounds we
        collect scores and set a conformal threshold, chosen so that only about 5 percent of
        honest scores would go above it. Lines 5 to 7: global means one limit for every
        client; Mondrian groups clients into 3 clusters with k-means and gives each cluster
        its own limit. That choice is our research question. Lines 9 to 11: if any of the
        three scores is above its limit, the update is flagged. Line 12: instead of throwing
        it away, a second check compares it with a trimmed mean of all updates; if it is
        close enough, it is rescued. Lines 15 to 17: the accepted updates are averaged, but
        no client may have more than 15 percent of the weight, so one large router cannot
        dominate.
    """, extra)


def s12_results(prs):
    slide = base(prs, "Results", "What the experiments show",
                 "Attack: 2 of 10 clients flip labels (attack ↔ normal) from round 6 of 12. "
                 "Means over 5 (FLNET2023) and 10 (NSL-KDD) seeds.")
    tiles = [
        (p(FED_ROUTER["accuracy"], 2), "FedAvg accuracy, 10 routers",
         f"centralized {p(CENTRAL['accuracy'])}"),
        (f"{PG['global']['tamper_rejected']} / {PG['global']['tamper_sent']}",
         "tampered messages rejected", "integrity tag"),
        (f"{p(FL['v2']['detection_rate_mean'])} · {p(NL['v2']['detection_rate_mean'])}",
         "poisoned updates caught", "FLNET2023 · NSL-KDD"),
        (f"{p(FL['v2']['false_positive_rate_mean'])} · {p(NL['v2']['false_positive_rate_mean'])}",
         "honest updates wrongly flagged", "FLNET2023 · NSL-KDD"),
    ]
    tw = Inches(2.95)
    for i, (num, lab, sub) in enumerate(tiles):
        x = LEFT + i * (tw + Inches(0.143))
        rect(slide, x, Inches(1.75), tw, Inches(1.35), fill=PANEL, line=LINE, radius=0.06)
        text(slide, x + Inches(0.2), Inches(1.85), tw - Inches(0.3), Inches(1.2),
             [[(num, {"size": 22, "font": HEAD, "color": ACCENT})],
              [(lab, {"size": 12})], [(sub, {"size": 10, "color": MUTED})]], spacing=1.1)
    bar_chart(slide, LEFT, Inches(3.3), Inches(6.0), Inches(3.6), ["FLNET2023", "NSL-KDD"],
              [("No protocol", [100 * FL["none"]["accuracy_mean"], 100 * NL["none"]["accuracy_mean"]]),
               ("With Krypsis", [100 * FL["v2"]["accuracy_mean"], 100 * NL["v2"]["accuracy_mean"]])],
              [MUTED, ACCENT], title="Accuracy under label-flipping attack", vmax=110, unit=20)
    bar_chart(slide, Inches(6.75), Inches(3.3), Inches(6.03), Inches(3.6),
              ["Centralized", "FedAvg IID", "FedAvg routers"],
              [("Macro-F1", [100 * MC["centralized"]["macro_f1"], 100 * MC["federated_iid"]["macro_f1"],
                             100 * MC["federated_router"]["macro_f1"]])],
              [AMBER], title="Naming the attack type (11 classes): macro-F1", fmt='0"%"',
              vmax=110, unit=20)
    notes(slide, f"""
        The results. Top left: federated training over the 10 routers reaches
        {p(FED_ROUTER['accuracy'], 2)}, almost the same as the centralized
        {p(CENTRAL['accuracy'])}. Every one of the 105 tampered messages was rejected. Under
        the label-flipping attack the protocol caught {p(FL['v2']['detection_rate_mean'])} of
        poisoned updates on FLNET2023 and {p(NL['v2']['detection_rate_mean'])} on NSL-KDD,
        while wrongly flagging under 1.2 percent of honest ones.
        Bottom left: accuracy at the end of an attacked run, without and with Krypsis:
        FLNET2023 {p(FL['none']['accuracy_mean'])} to {p(FL['v2']['accuracy_mean'])}, NSL-KDD
        {p(NL['none']['accuracy_mean'])} to {p(NL['v2']['accuracy_mean'])}; the NSL-KDD gain is
        statistically significant, p = 0.009.
        Bottom right: the binary task is easy, so we also named the 11 traffic types. There,
        real uneven routers drop macro-F1 from 0.76 to 0.39: attack types that only one
        router sees get averaged away. That is the cost of non-IID data.
    """)


def s13_comparison(prs):
    slide = base(prs, "Comparison  ·  research question", "No protocol vs global vs Mondrian",
                 "FLNET2023, 2 of 10 attackers, 15 seeds, paired t-tests.")
    n, g, m = PG["none"], PG["global"], PG["mondrian"]
    pt = PG["paired_t_test_global_vs_mondrian"]
    cols = [("No protocol", False), ("Protocol + global", True), ("Protocol + Mondrian", False)]
    rows = [("Accuracy under attack", [p(n["final_accuracy_mean"]), p(g["final_accuracy_mean"]),
                                       p(m["final_accuracy_mean"])]),
            ("Attacks caught", ["—", p(g["detection_rate_mean"]), p(m["detection_rate_mean"])]),
            ("Honest wrongly flagged", ["—", p(g["false_positive_rate_mean"]),
                                        p(m["false_positive_rate_mean"])]),
            ("Tampered rejected", ["not checked", f"{g['tamper_rejected']} / {g['tamper_sent']}",
                                   f"{m['tamper_rejected']} / {m['tamper_sent']}"])]
    x0, y0 = LEFT, Inches(1.85)
    lw, cw, rh = Inches(3.4), Inches(2.6), Inches(0.72)
    for j, (name, best) in enumerate(cols):
        x = x0 + lw + j * (cw + Inches(0.1))
        rect(slide, x, y0, cw, rh * (len(rows) + 1) + Inches(0.1),
             fill=ACCENT_DIM if best else PANEL, line=ACCENT if best else None, radius=0.05)
        text(slide, x, y0, cw, rh, name, size=14, bold=True, font=HEAD,
             color=ACCENT if best else TEXT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        if best:
            pill(slide, x + cw / 2 - Inches(0.45), y0 - Inches(0.17), Inches(0.9),
                 Inches(0.3), "BEST", fill=ACCENT, color=BG, size=10, font=HEAD)
    for i, (lab, vals) in enumerate(rows):
        y = y0 + (i + 1) * rh
        line(slide, x0, y, x0 + lw + 3 * cw + Inches(0.2), y, color=LINE, weight=0.75)
        text(slide, x0, y, lw, rh, lab, size=14, color=SOFT, anchor=MSO_ANCHOR.MIDDLE)
        for j, v in enumerate(vals):
            x = x0 + lw + j * (cw + Inches(0.1))
            text(slide, x, y, cw, rh, v, size=17, font=HEAD,
                 color=ACCENT if cols[j][1] else TEXT, bold=cols[j][1],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    rect(slide, LEFT, Inches(5.75), CONTENT_W, Inches(1.0), fill=PANEL, radius=0.08)
    rect(slide, LEFT, Inches(5.75), Inches(0.06), Inches(1.0), fill=AMBER)
    text(slide, LEFT + Inches(0.3), Inches(5.75), CONTENT_W - Inches(0.5), Inches(1.0), [
        [("Answer: no.  ", {"bold": True, "color": AMBER, "font": HEAD, "size": 15}),
         ("Mondrian caught a little more but flagged more honest clients; neither difference "
          f"is significant (p = {pt['detection_rate']['p_value']:.2f} and "
          f"{pt['false_positive_rate']['p_value']:.2f}). One global threshold is enough.",
          {"size": 13.5})]], anchor=MSO_ANCHOR.MIDDLE, spacing=1.2)
    notes(slide, f"""
        This answers our research question, using the dedicated 15-seed experiment on
        FLNET2023. Without the protocol, accuracy under attack ends at
        {p(n['final_accuracy_mean'])}. With the protocol and a global threshold it is
        {p(g['final_accuracy_mean'])}; with Mondrian {p(m['final_accuracy_mean'])}. Mondrian
        caught slightly more attacks, {p(m['detection_rate_mean'])} against
        {p(g['detection_rate_mean'])}, but also wrongly flagged more honest clients,
        {p(m['false_positive_rate_mean'])} against {p(g['false_positive_rate_mean'])}. Paired
        t-tests over the 15 seeds show neither difference is significant. So the simpler
        global threshold is the best choice, and both rejected every tampered message.
    """)


def s14_conclusion(prs):
    slide = base(prs, "Conclusion", "What we built and what we learned")
    items = [
        ("Built", "A federated intrusion detector over 10 real router clients, with our own "
                  "update protocol."),
        ("Protocol", "HMAC tag + verifiable fingerprint: all tampering rejected, poisoned "
                     "updates filtered, +0.67% size."),
        ("Accuracy", "Federated nearly matches centralized; under attack Krypsis keeps "
                     "accuracy higher."),
        ("Finding", "One global threshold is enough; Mondrian gave no significant gain."),
        ("Next", "Protocol on the 11-class task, a trust-based weight cap, a real network "
                 "testbed."),
    ]
    for i, (k, v) in enumerate(items):
        y = Inches(1.6) + i * Inches(0.82)
        pill(slide, LEFT, y + Inches(0.08), Inches(1.25), Inches(0.36), k.upper(),
             fill=AMBER_DIM if k == "Next" else ACCENT_DIM,
             color=AMBER if k == "Next" else ACCENT, size=10.5, font=HEAD)
        text(slide, LEFT + Inches(1.5), y, Inches(5.9), Inches(0.75), v, size=13.5,
             anchor=MSO_ANCHOR.TOP, spacing=1.15)
    x = Inches(8.1)
    rect(slide, x, Inches(1.55), Inches(4.68), Inches(5.3), fill=PANEL, radius=0.04)
    text(slide, x + Inches(0.25), Inches(1.7), Inches(4), Inches(0.3), "KEY REFERENCES",
         size=11, bold=True, color=MUTED, font=HEAD)
    refs = [
        ("FLNET2023 dataset, MILCOM 2023", "https://doi.org/10.1109/MILCOM58377.2023.10356272"),
        ("McMahan et al. 2017 · FedAvg", "https://arxiv.org/abs/1602.05629"),
        ("Hsu et al. 2019 · Dirichlet non-IID", "https://arxiv.org/abs/1909.06335"),
        ("Angelopoulos & Bates 2021 · conformal", "https://arxiv.org/abs/2107.07511"),
        ("Blanchard et al. 2017 · Krum", "https://arxiv.org/abs/1703.02757"),
        ("Yin et al. 2018 · trimmed mean", "https://arxiv.org/abs/1803.01498"),
        ("Tolpegin et al. 2020 · label flipping", "https://arxiv.org/abs/2007.08432"),
        ("RFC 2104 · HMAC", "https://www.rfc-editor.org/rfc/rfc2104"),
    ]
    for i, (name, url) in enumerate(refs):
        y = Inches(2.1) + i * Inches(0.58)
        box = text(slide, x + Inches(0.25), y, Inches(4.25), Inches(0.55),
                   [[(name, {"size": 11.5})], [(url, {"size": 9, "color": ACCENT})]],
                   spacing=1.05)
        box.text_frame.paragraphs[1].runs[0].hyperlink.address = url
    text(slide, LEFT, Inches(5.95), Inches(7.2), Inches(0.8), [
        [("Thank you", {"size": 26, "font": HEAD})],
        [("Questions welcome  ·  code: github.com/Vinudharshini18", {"size": 11.5,
                                                                    "color": MUTED})]],
         spacing=1.1)
    notes(slide, """
        To conclude. We built a federated intrusion detector over 10 real router clients
        and our own protocol for the model updates. The protocol rejected every tampered
        message and filtered poisoned updates for less than 1 percent extra message size.
        Federated training almost matches centralized training, and under attack Krypsis
        keeps accuracy higher. Our research finding: one global threshold is enough; the
        per-cluster Mondrian threshold gave no significant gain. Next we would run the
        protocol on the 11-class task, use a trust-based weight cap, and test on a real
        network. The key references are on the right, and all the code and results are on
        GitHub. Thank you, we are happy to take questions.
    """)


def _link_colors(prs):
    """Hyperlinks in the theme colour, not the default blue."""
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    theme = prs.slide_master.part.part_related_by(RT.THEME)
    xml = theme.blob.decode("utf-8")
    for tag in ("hlink", "folHlink"):
        xml = re.sub(rf"(<a:{tag}>\s*<a:srgbClr val=\")[0-9A-Fa-f]{{6}}", rf"\g<1>{ACCENT}", xml)
    theme._blob = xml.encode("utf-8")


def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    for make in (s01_title, s02_problem, s03_overview, s04_data, s05_clients, s06_model,
                 s07_fedavg, s08_message, s09_verify, s10_scoring, s11_threshold,
                 s12_results, s13_comparison, s14_conclusion):
        make(prs)
    assert len(prs.slides) == TOTAL
    _link_colors(prs)
    prs.save(OUT_PATH)
    print(f"Saved {OUT_PATH} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    build()
