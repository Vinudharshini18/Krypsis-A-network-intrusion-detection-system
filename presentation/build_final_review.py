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

# Same look as the first class deck (build_deck.py): sage paper, deep ink,
# teal accent, warm orange highlights, white bordered cards.
BG = RGBColor(0xF2, 0xF4, 0xF0)
BG_DEEP = RGBColor(0xE7, 0xEB, 0xE4)
PANEL = RGBColor(0xFF, 0xFF, 0xFF)
PANEL_2 = RGBColor(0xE7, 0xEB, 0xE4)
CODE_BG = RGBColor(0xFF, 0xFF, 0xFF)
LINE = RGBColor(0xCF, 0xD6, 0xCB)
TEXT = RGBColor(0x17, 0x24, 0x20)
SOFT = RGBColor(0x56, 0x65, 0x5D)
MUTED = RGBColor(0x8A, 0x96, 0x8F)
ACCENT = RGBColor(0x14, 0x6B, 0x62)
ACCENT_DIM = RGBColor(0xD7, 0xEB, 0xE7)
AMBER = RGBColor(0xC9, 0x7A, 0x2B)
AMBER_DIM = RGBColor(0xF5, 0xE2, 0xC8)
CORAL = RGBColor(0xC9, 0x7A, 0x2B)
# syntax colours
KW = RGBColor(0x14, 0x6B, 0x62)
STR = RGBColor(0x9A, 0x5B, 0x13)
NUM = RGBColor(0xC9, 0x7A, 0x2B)
FN = RGBColor(0x2E, 0x55, 0x8A)

HEAD = "Calibri"
BODY = "Calibri"
DISPLAY = "Arial Black"
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
    if line is None and fill == PANEL:
        line = LINE
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
        tw = Inches(0.4 + 0.085 * len(tag))
        rect(slide, LEFT, Inches(0.32), tw, Inches(0.32), fill=ACCENT_DIM, radius=0.5)
        text(slide, LEFT, Inches(0.32), tw, Inches(0.32), tag.upper(), size=10.5, bold=True,
             color=ACCENT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, LEFT, Inches(0.72), CONTENT_W, Inches(0.55), title, size=26,
             font=DISPLAY)
        if subtitle:
            text(slide, LEFT, Inches(1.27), CONTENT_W, Inches(0.4), subtitle, size=14,
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
            runs.append((word, {"color": KW, "bold": True}))
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
               h=Inches(5.12), size_cap=CODE_SIZE):
    lines = textwrap.dedent(source).strip("\n").split("\n")
    assert max(len(s) for s in lines) <= 70, max(lines, key=len)
    # Shrink the type a little when a snippet is long, so it always fits.
    leading = min(CODE_LEADING, size_cap * 1.32,
                  (h - Inches(0.75)) / 914400 * 72 / len(lines))
    size = min(size_cap, leading / 1.32)
    assert max(len(s) for s in lines) * size * 0.55 / 72 <= (w - Inches(0.9)) / 914400, \
        (filename, "code too wide")
    rect(slide, x, y, w, h, fill=CODE_BG, line=LINE, radius=0.025)
    rect(slide, x, y, w, Inches(0.42), fill=PANEL_2, radius=None)
    text(slide, x + Inches(0.25), y, w - Inches(1.1), Inches(0.42), filename, size=11,
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
    rect(slide, 0, 0, W, H, fill=BG_DEEP)
    text(slide, LEFT + Inches(0.1), Inches(1.2), Inches(9), Inches(0.3),
         "COMPUTER NETWORKS  —  FINAL PROJECT REVIEW", size=12, bold=True, color=AMBER,
         font=HEAD)
    text(slide, LEFT + Inches(0.1), Inches(1.4), Inches(7.5), Inches(1.4), "KRYPSIS", size=72,
         font=DISPLAY, color=TEXT)
    text(slide, LEFT + Inches(0.1), Inches(2.85), Inches(7.0), Inches(1.0),
         "Federated network intrusion detection with a\nsecurity-fused model-update protocol",
         size=20, color=SOFT, spacing=1.2)
    line(slide, LEFT + Inches(0.1), Inches(4.85), LEFT + Inches(7.0), Inches(4.85))
    team = [("Rithika K", "CB.SC.U4AIE25126"), ("Pradhaniya S", "CB.SC.U4AIE25148"),
            ("Sathya K", "CB.SC.U4AIE25154"), ("Vinudharshini PP", "CB.SC.U4AIE25161")]
    for i, (name, roll) in enumerate(team):
        col, row = i % 2, i // 2
        text(slide, LEFT + Inches(0.1) + col * Inches(3.5), Inches(5.1) + row * Inches(0.8),
             Inches(3.3), Inches(0.75),
             [[(name, {"bold": True, "size": 15, "font": HEAD})],
              [(roll, {"size": 12, "color": SOFT})]], spacing=1.1)

    notes(slide, """
        Good morning. Our project is Krypsis: a network intrusion detection system trained
        with federated learning across 10 routers, protected by our own update protocol.
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
                 "Each step is one of the next slides, explained with a diagram.")
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


# ------------------------------------------------------------------ diagram helpers

def box(slide, x, y, w, h, title, body=None, fill=PANEL, line_c=LINE, title_color=TEXT,
        size=13, body_size=10.5, radius=0.1, body_color=SOFT):
    rect(slide, x, y, w, h, fill=fill, line=line_c, radius=radius)
    content = [[(title, {"bold": True, "size": size, "color": title_color})]]
    if body:
        content.append([(body, {"size": body_size, "color": body_color})])
    text(slide, x + Inches(0.08), y, w - Inches(0.16), h, content, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE, spacing=1.05)


def diamond(slide, x, y, w, h, label):
    rect(slide, x, y, w, h, fill=ACCENT_DIM, line=ACCENT, shape=MSO_SHAPE.DIAMOND)
    text(slide, x + Inches(0.2), y, w - Inches(0.4), h, label, size=11, bold=True,
         color=ACCENT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=1.0)


def points(slide, x, y, w, items, size=12, gap=Inches(0.12), heading=None):
    """items: (bold lead, body). A small accent square marks each point."""
    if heading:
        text(slide, x, y, w, Inches(0.3), heading, size=11, bold=True, color=MUTED)
        y += Inches(0.38)
    for lead, body in items:
        rect(slide, x, y + Inches(0.08), Inches(0.1), Inches(0.1), fill=ACCENT)
        per_line = (w / 914400 - 0.25) * 72 / (size * 0.48)
        n_lines = math.ceil((len(lead) + 2 + len(body)) / per_line)
        h = Inches(n_lines * size * 1.3 / 72)
        text(slide, x + Inches(0.25), y, w - Inches(0.25), h,
             [[(lead + "  ", {"bold": True}), (body, {"color": SOFT})]], size=size,
             spacing=1.1)
        y += h + gap
    return y


def label_caps(slide, x, y, w, content, color=MUTED):
    text(slide, x, y, w, Inches(0.3), content.upper(), size=11, bold=True, color=color)


def vec(slide, x, y, length, angle_deg, color=SOFT, weight=1.75):
    a = math.radians(angle_deg)
    line(slide, x, y, x + length * math.cos(a), y - length * math.sin(a), color=color,
         weight=weight, head=True)


IID_ATTACK = [66.0, 66.3, 65.7, 65.6, 65.8, 65.8, 66.3, 65.6, 66.1, 66.1]
DIRICHLET_ATTACK = [28.0, 100.0, 99.2, 18.4, 40.2, 97.6, 40.2, 11.9, 84.1, 54.3]
TRAFFIC_TYPES = [("Normal", 192253), ("DoS-hulk", 164438), ("DDoS-tcp", 93080),
                 ("DDoS-stomp", 38954), ("DDoS-dyn", 32292), ("Infiltration-MITM", 16000),
                 ("DoS-slowhttp", 14369), ("DDoS-bot", 8781), ("Web-XSS", 3069),
                 ("Web-SQL-injection", 441), ("Web-cmd-injection", 330)]


def mtag(step):
    return f"Methodology  ·  step {step} of 8"


# ------------------------------------------------------------------ methodology

def s04_data(prs):
    slide = base(prs, mtag(1), "Data and preprocessing",
                 "FLNET2023 records network flows at 10 routers. Five steps turn the raw "
                 "captures into clean model input.")
    stages = [("Raw captures", "one CSV set per router · 4.8 M flows"),
              ("Sample 10%", "at least 2,000 rows per file"),
              ("Drop identifiers", "src/dst IP, source port, timestamp"),
              ("Clean", "inf / NaN rows · 12 constant columns"),
              ("Scale", "signed log, then min-max to 0–1"),
              ("Model input", "66 features · label 0 / 1")]
    bw, gap = Inches(1.86), Inches(0.215)
    for i, (t, b) in enumerate(stages):
        x = LEFT + i * (bw + gap)
        last = i == len(stages) - 1
        box(slide, x, Inches(1.85), bw, Inches(1.1), t, b,
            fill=ACCENT_DIM if last else PANEL, line_c=ACCENT if last else LINE,
            title_color=ACCENT if last else TEXT)
        if not last:
            line(slide, x + bw, Inches(2.4), x + bw + gap, Inches(2.4), color=ACCENT,
                 head=True)

    points(slide, LEFT, Inches(3.3), Inches(5.9), [
        ("Why sample?", "4.8 million flows is too many to train hundreds of federated "
                        "runs on a laptop; 10% keeps every router's mix of traffic."),
        ("Why drop identifiers?", "Attackers in the capture use fixed addresses. With IPs "
                                  "and time left in, the model would memorise who attacks, "
                                  "not what an attack looks like."),
        ("Why log scaling?", "Byte and packet counts range from 1 to about a billion; "
                             "the log stops a few huge flows from squashing the rest."),
        ("No test leakage", "The scaler is fitted on training data only. Result: 564,007 "
                            "training and 79,491 test flows."),
    ], heading="Why each step")

    x0, w0 = Inches(6.85), Inches(5.93)
    rect(slide, x0, Inches(3.3), w0, Inches(3.55), fill=PANEL, radius=0.04)
    label_caps(slide, x0 + Inches(0.25), Inches(3.42), Inches(5), "Training flows by type")
    top = max(n for _, n in TRAFFIC_TYPES)
    bar_x, bar_w = x0 + Inches(1.85), Inches(2.9)
    for i, (name, n) in enumerate(TRAFFIC_TYPES):
        y = Inches(3.78) + i * Inches(0.27)
        text(slide, x0 + Inches(0.2), y, Inches(1.6), Inches(0.24), name, size=10,
             color=TEXT, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
        bw_ = max(Inches(0.03), bar_w * n / top)
        rect(slide, bar_x, y + Inches(0.04), bw_, Inches(0.17),
             fill=MUTED if name == "Normal" else ACCENT)
        text(slide, bar_x + bw_ + Inches(0.08), y, Inches(1.0), Inches(0.24), f"{n:,}",
             size=9.5, color=SOFT, anchor=MSO_ANCHOR.MIDDLE)
    notes(slide, """
        Step one is the data. FLNET2023 was recorded at 10 routers of an emulated network and
        has normal traffic plus 10 attack types: the chart on the right shows how many training
        flows of each type we have. Most are normal, DoS-hulk and DDoS-tcp; web attacks are
        rare.
        The top row is our preprocessing. We sample 10 percent of each file, because the full
        4.8 million flows is too big to train many times. We drop IP addresses, the port and the
        timestamp, so the model learns what an attack looks like instead of memorising the
        attacker's address. We remove broken rows and 12 columns that never change. Then a log
        and a 0 to 1 scaling, fitted only on the training data. The result is 66 features per
        flow and a label: 0 for normal, 1 for attack.
    """)


def s05_clients(prs):
    slide = base(prs, mtag(2), "Client split: who holds which data",
                 "IID means every client has a similar mix. Non-IID means every client is "
                 "different, as in real networks.")
    cols = [
        ("IID split", "control", IID_ATTACK, MUTED,
         "All flows shuffled and dealt out evenly. Every client is about 66% attack, so "
         "everyone looks alike."),
        ("Router split", "FLNET2023 · main", ROUTER_ATTACK, ACCENT,
         "Each real router is one client. Router 3 sees 19% attacks, router 4 sees 92%: "
         "naturally uneven."),
        ("Dirichlet split", "NSL-KDD · alpha = 0.5", DIRICHLET_ATTACK, AMBER,
         "Each attack type is shared out with random Dirichlet proportions. Smaller alpha "
         "= more uneven clients."),
    ]
    cw, gap = Inches(3.93), Inches(0.22)
    for i, (title, sub, vals, color, body) in enumerate(cols):
        x = LEFT + i * (cw + gap)
        rect(slide, x, Inches(1.85), cw, Inches(4.15), fill=PANEL, radius=0.04)
        text(slide, x + Inches(0.25), Inches(1.98), cw - Inches(0.5), Inches(0.6),
             [[(title, {"bold": True, "size": 15})], [(sub, {"size": 10.5, "color": MUTED})]],
             spacing=1.05)
        text(slide, x + Inches(0.25), Inches(2.62), cw, Inches(0.25),
             "attack % in each client's data", size=9.5, color=MUTED)
        mini_bars(slide, x + Inches(0.2), Inches(2.85), cw - Inches(0.4), Inches(1.85), vals,
                  [str(k) for k in range(1, 11)], color=color)
        text(slide, x + Inches(0.25), Inches(4.9), cw - Inches(0.5), Inches(1.0), body,
             size=11.5, color=SOFT, spacing=1.15)
    rect(slide, LEFT, Inches(6.18), CONTENT_W, Inches(0.68), fill=AMBER_DIM, radius=0.1)
    rect(slide, LEFT, Inches(6.18), Inches(0.06), Inches(0.68), fill=AMBER)
    text(slide, LEFT + Inches(0.3), Inches(6.18), CONTENT_W - Inches(0.5), Inches(0.68), [
        [("Why it matters  ", {"bold": True, "color": AMBER}),
         ("An honest client with unusual data can look like an attacker to an outlier "
          "check. That is exactly our research question.", {})]], size=12.5,
         anchor=MSO_ANCHOR.MIDDLE)
    notes(slide, """
        Step two decides which data each client holds. The three charts show the share of
        attack traffic at each of the 10 clients.
        Left, the IID split: we shuffle all flows and deal them out evenly, so every client is
        about 66 percent attack. This is only a control.
        Middle, our main setup: FLNET2023's real routers, one router per client. It is uneven by
        nature: router 3 has 19 percent attacks, router 4 has 92.
        Right, NSL-KDD with a Dirichlet split. For each attack type, a Dirichlet distribution
        with alpha 0.5 gives every client a random share, so some clients are almost all attack
        and others almost all normal.
        This matters because a protocol that rejects unusual updates might reject an honest
        router just because its traffic is different.
    """)


def s06_model(prs):
    slide = base(prs, mtag(3), "Model: a multilayer perceptron",
                 "One small neural network, used for the centralized baseline and copied to "
                 "every client.")
    # Neural network drawing.
    cols = [(7, "Input", "66 features"), (8, "Dense 256", "ReLU · dropout 0.3"),
            (7, "Dense 128", "ReLU · dropout 0.3"), (6, "Dense 64", "ReLU · dropout 0.2"),
            (1, "Output", "sigmoid → P(attack)")]
    area_x, area_w = LEFT + Inches(0.35), Inches(6.2)
    top, bottom = Inches(2.0), Inches(5.6)
    d = Inches(0.26)
    xs = [area_x + area_w * i / (len(cols) - 1) for i in range(len(cols))]
    centres = []
    for (n, _, _), x in zip(cols, xs):
        step = (bottom - top) / 8
        y0 = (top + bottom) / 2 - step * (n - 1) / 2
        centres.append([(x, y0 + k * step) for k in range(n)])
    for a, b in zip(centres, centres[1:]):
        for (x1, y1) in a:
            for (x2, y2) in b:
                line(slide, x1, y1, x2, y2, color=LINE, weight=0.5)
    for i, nodes in enumerate(centres):
        for (x, y) in nodes:
            rect(slide, x - d / 2, y - d / 2, d, d, shape=MSO_SHAPE.OVAL,
                 fill=ACCENT if i in (1, 2, 3) else (AMBER if i == 4 else PANEL),
                 line=ACCENT if i in (1, 2, 3) else (AMBER if i == 4 else MUTED))
    for (n, t, b), x in zip(cols, xs):
        text(slide, x - Inches(0.75), Inches(5.85), Inches(1.5), Inches(0.7),
             [[(t, {"bold": True, "size": 12})], [(b, {"size": 9.5, "color": SOFT})]],
             align=PP_ALIGN.CENTER, spacing=1.05)
    points(slide, Inches(8.1), Inches(1.85), Inches(4.68), [
        ("Why an MLP?", "Flow features are a flat table of numbers; a dense network fits "
                        "them well and averages cleanly under FedAvg."),
        ("Hidden layers", "256 → 128 → 64 neurons with ReLU learn combinations of "
                          "packet, byte and timing features."),
        ("Against overfitting", "Dropout switches off random neurons while training; L2 "
                                "keeps the weights small."),
        ("Output", "One sigmoid neuron gives the probability that a flow is an attack."),
        ("Size", "58,369 weights: exactly what each client sends every round."),
        ("Baseline", "Trained centrally with class weights, early stopping and a tuned "
                     "threshold: the best accuracy to aim for."),
    ], size=12, heading="Design choices")
    notes(slide, """
        Step three is the model, a multilayer perceptron, drawn on the left. The input is the
        66 features of one flow. Three hidden layers of 256, 128 and 64 neurons learn
        combinations of those features, using the ReLU activation. Dropout randomly switches
        off neurons during training and L2 keeps the weights small; both stop the model from
        memorising. The single output neuron uses a sigmoid to give the probability of an
        attack.
        We chose an MLP because our data is a table of numbers, and its weights average
        cleanly in federated learning. It has 58,369 weights, and that is exactly the update
        each client sends every round. Trained on all the data in one place, it is our
        centralized baseline.
    """)


def s07_fedavg(prs):
    slide = base(prs, mtag(4), "Federated training with FedAvg",
                 "Every round: send the model out, train locally, send weights back, "
                 "average. Raw traffic never leaves a router.")
    cx, cy = Inches(4.1), Inches(4.25)
    r = Inches(0.62)
    rect(slide, cx - r, cy - r, 2 * r, 2 * r, shape=MSO_SHAPE.OVAL, fill=ACCENT_DIM,
         line=ACCENT, line_w=1.5)
    text(slide, cx - r, cy - r, 2 * r, 2 * r, "Server", size=13, bold=True, color=ACCENT,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    bw, bh = Inches(2.45), Inches(0.95)
    spots = [(cx, Inches(2.35), "1 · Send global model", "server → all 10 routers"),
             (Inches(6.6), cy, "2 · Train locally", "2 epochs on own traffic"),
             (cx, Inches(6.15), "3 · Send weights back", "new weights + sample count"),
             (Inches(1.6), cy, "4 · Weighted average", "FedAvg → new global model")]
    for (x, y, t, b) in spots:
        box(slide, x - bw / 2, y - bh / 2, bw, bh, t, b, size=12.5)
    hw, hh = bw / 2, bh / 2
    line(slide, cx + hw, Inches(2.35), Inches(6.6), cy - hh, color=ACCENT, head=True)
    line(slide, Inches(6.6), cy + hh, cx + hw, Inches(6.15), color=ACCENT, head=True)
    line(slide, cx - hw, Inches(6.15), Inches(1.6), cy + hh, color=ACCENT, head=True)
    line(slide, Inches(1.6), cy - hh, cx - hw, Inches(2.35), color=ACCENT, head=True)

    x0, w0 = Inches(8.0), Inches(4.78)
    rect(slide, x0, Inches(1.85), w0, Inches(1.35), fill=PANEL, radius=0.06)
    label_caps(slide, x0 + Inches(0.25), Inches(1.95), w0, "The FedAvg rule")
    text(slide, x0 + Inches(0.25), Inches(2.25), w0 - Inches(0.4), Inches(0.5),
         [[("new model = Σ  (n", {}), ("k", {"size": 12}), (" / n) × model", {}),
           ("k", {"size": 12})]], size=19, color=ACCENT, bold=True)
    text(slide, x0 + Inches(0.25), Inches(2.75), w0 - Inches(0.4), Inches(0.4),
         "nk = flows at router k, n = all flows: bigger routers count more.", size=10.5,
         color=SOFT)
    points(slide, x0, Inches(3.45), w0, [
        ("Why weighted?", "A router with more traffic has seen more examples, so its model "
                          "counts more. Router 10 holds 25% of all flows."),
        ("Setup", "10 clients · 15 rounds · 2 local epochs · batch size 256."),
        ("Privacy", "Only the 58,369 weights travel; the 564,007 flows stay on their "
                    "routers."),
        ("Result", f"{p(FED_ROUTER['accuracy'], 2)} over the real routers vs "
                   f"{p(CENTRAL['accuracy'])} centralized."),
        ("Where Krypsis fits", "Steps 5–8 run between 3 (send back) and 4 (average)."),
    ], size=12)
    notes(slide, """
        Step four is federated training, a loop that repeats every round. One: the server
        sends the current global model to all 10 routers. Two: each router trains it for two
        epochs on its own traffic. Three: each router sends back only its new weights and how
        many flows it trained on. Four: the server averages them with the FedAvg rule on the
        right: each router's model is weighted by its share of the data, so a router with more
        traffic counts more.
        After 15 rounds the federated model reaches 99.93 percent, almost the same as training
        on all data in one place. In the protected version, steps five to eight happen between
        "send weights back" and "average".
    """)


def s08_message(prs):
    slide = base(prs, mtag(5), "The Krypsis message",
                 "After local training, each client wraps its update in one message with a "
                 "fingerprint and an integrity tag.")
    parts = [("Length", "4 bytes", "where the header ends", Inches(1.5), PANEL_2, TEXT),
             ("Header + fingerprint", "≈1.5 KB", "client · round · sample count · "
              "fingerprint", Inches(3.7), ACCENT_DIM, ACCENT),
             ("Payload", f"{COMM['raw_payload_bytes']:,} bytes",
              "the update Δw: 58,369 float32 numbers", Inches(4.6), PANEL, TEXT),
             ("Integrity tag", "32 bytes", "HMAC-SHA256", Inches(2.43), AMBER_DIM, AMBER)]
    x = LEFT
    for name, size_, body, w, fill, col in parts:
        rect(slide, x, Inches(1.85), w, Inches(1.05), fill=fill, line=LINE)
        text(slide, x + Inches(0.15), Inches(1.9), w - Inches(0.3), Inches(1.0),
             [[(name, {"bold": True, "size": 13, "color": col}),
               ("   " + size_, {"size": 11, "color": SOFT})],
              [(body, {"size": 10.5, "color": SOFT})]], anchor=MSO_ANCHOR.MIDDLE,
             spacing=1.15)
        x += w

    # Fingerprint panel.
    fx, fw = LEFT, Inches(6.0)
    rect(slide, fx, Inches(3.15), fw, Inches(3.7), fill=PANEL, radius=0.04)
    label_caps(slide, fx + Inches(0.25), Inches(3.27), fw, "The fingerprint: a short summary",
               color=ACCENT)
    rect(slide, fx + Inches(0.4), Inches(3.75), Inches(0.35), Inches(2.3), fill=MUTED)
    text(slide, fx + Inches(0.1), Inches(6.1), Inches(1.0), Inches(0.5),
         "Δw\n58,369", size=10, color=SOFT, align=PP_ALIGN.CENTER, spacing=1.0)
    line(slide, fx + Inches(0.85), Inches(4.9), fx + Inches(2.45), Inches(4.9),
         color=ACCENT, head=True)
    text(slide, fx + Inches(0.8), Inches(4.25), Inches(1.75), Inches(0.6),
         "× random matrix\n(public seed 2023)", size=10, color=SOFT, align=PP_ALIGN.CENTER,
         spacing=1.0)
    outs = [("sketch", "64 numbers: the update's direction", Inches(0.9)),
            ("L2 norm", "1 number: overall size", Inches(0.25)),
            ("layer norms", "4 numbers: size per layer", Inches(0.45))]
    y = Inches(3.8)
    for name, desc, h in outs:
        rect(slide, fx + Inches(2.6), y, Inches(0.35), h, fill=ACCENT)
        text(slide, fx + Inches(3.1), y - Inches(0.03), Inches(2.8), Inches(0.5),
             [[(name, {"bold": True, "size": 12})], [(desc, {"size": 10.5, "color": SOFT})]],
             spacing=1.0)
        y += max(h, Inches(0.55)) + Inches(0.25)
    text(slide, fx + Inches(2.6), Inches(6.2), Inches(3.3), Inches(0.55),
         "The server can recompute it, so it cannot be faked.", size=10.5, color=ACCENT)

    # Integrity tag panel.
    tx, tw = Inches(6.78), Inches(6.0)
    rect(slide, tx, Inches(3.15), tw, Inches(3.7), fill=PANEL, radius=0.04)
    label_caps(slide, tx + Inches(0.25), Inches(3.27), tw, "The integrity tag: a digital seal",
               color=AMBER)
    box(slide, tx + Inches(0.3), Inches(3.8), Inches(1.9), Inches(0.75), "header + payload",
        size=11.5)
    box(slide, tx + Inches(0.3), Inches(4.75), Inches(1.9), Inches(0.75), "secret key",
        "32 bytes, one per client", size=11.5)
    box(slide, tx + Inches(2.75), Inches(4.25), Inches(1.45), Inches(0.8), "HMAC", "SHA-256",
        fill=AMBER_DIM, line_c=AMBER, title_color=AMBER, size=13)
    box(slide, tx + Inches(4.6), Inches(4.3), Inches(1.15), Inches(0.7), "tag", "32 bytes",
        size=12)
    line(slide, tx + Inches(2.2), Inches(4.17), tx + Inches(2.75), Inches(4.5), color=AMBER,
         head=True)
    line(slide, tx + Inches(2.2), Inches(5.12), tx + Inches(2.75), Inches(4.8), color=AMBER,
         head=True)
    line(slide, tx + Inches(4.2), Inches(4.65), tx + Inches(4.6), Inches(4.65), color=AMBER,
         head=True)
    text(slide, tx + Inches(0.3), Inches(5.75), tw - Inches(0.6), Inches(1.0),
         "Only the client and the server know the key. Change even one byte on the way and "
         f"the tag no longer matches. Total cost: +{p(COMM['krypsis_overhead_bytes'] / COMM['raw_payload_bytes'], 2)} "
         f"message size (plain JSON would be {COMM['http_json_bytes'] / COMM['raw_payload_bytes']:.1f}× bigger).",
         size=11, color=SOFT, spacing=1.15)
    notes(slide, """
        Step five is our protocol on the client. After training, the client wraps its update in
        one message, shown on top: a length field, a header with the fingerprint, the update
        itself as raw numbers, and the integrity tag at the end.
        Left: the fingerprint is a short summary of the update. The 58,369 numbers are
        multiplied by a fixed random matrix, made from a public seed, which squeezes them into
        64 numbers that keep the update's direction. We add the overall size and the size per
        layer. Because the seed is public, the server can recompute the fingerprint and check
        it.
        Right: the integrity tag. The header and payload are run through HMAC with SHA-256,
        together with a secret key that only this client and the server know. If anyone changes
        even one byte on the way, the tag will not match. All of this adds only 0.67 percent to
        the message size.
    """)


def s09_verify(prs):
    slide = base(prs, mtag(6), "Server verification: two hard checks",
                 "Before anything else, the server checks that the message is genuine. "
                 "Failures are dropped immediately.")
    y, h = Inches(2.35), Inches(1.2)
    box(slide, LEFT, y, Inches(1.8), h, "Message arrives", "from client k")
    box(slide, Inches(2.75), y, Inches(2.0), h, "Split it", "length · header · payload · tag")
    diamond(slide, Inches(5.1), y - Inches(0.15), Inches(2.3), h + Inches(0.3),
            "Tag\nmatches?")
    diamond(slide, Inches(7.85), y - Inches(0.15), Inches(2.3), h + Inches(0.3),
            "Fingerprint\nmatches?")
    box(slide, Inches(10.6), y, Inches(2.18), h, "Accepted", "go to scoring (step 7)",
        fill=ACCENT_DIM, line_c=ACCENT, title_color=ACCENT)
    mid = y + h / 2
    for x1, x2 in ((LEFT + Inches(1.8), Inches(2.75)), (Inches(4.75), Inches(5.1)),
                   (Inches(7.4), Inches(7.85)), (Inches(10.15), Inches(10.6))):
        line(slide, x1, mid, x2, mid, color=ACCENT, head=True)
    for x, lab in ((Inches(7.4), "yes"), (Inches(10.15), "yes")):
        text(slide, x - Inches(0.05), mid - Inches(0.32), Inches(0.5), Inches(0.25), lab,
             size=10, color=ACCENT, bold=True)
    for cxx, lab, why in ((Inches(6.25), "Reject: bad_tag", "changed on the way"),
                          (Inches(9.0), "Reject: fingerprint_mismatch", "client lied")):
        line(slide, cxx, y + h + Inches(0.15), cxx, Inches(4.25), color=AMBER, head=True)
        text(slide, cxx + Inches(0.08), Inches(3.8), Inches(0.4), Inches(0.25), "no",
             size=10, color=AMBER, bold=True)
        box(slide, cxx - Inches(1.2), Inches(4.25), Inches(2.4), Inches(0.75), lab, why,
            fill=AMBER_DIM, line_c=AMBER, title_color=AMBER, size=11.5)

    points(slide, LEFT, Inches(5.3), Inches(5.25), [
        ("Check 1 · tag", "The server recomputes the HMAC with that client's key and "
                          "compares in constant time."),
        ("Check 2 · fingerprint", "It recomputes the fingerprint from the payload instead of "
                                  "trusting the header."),
    ], size=12)
    code_panel(slide, '''
        if not hmac.compare_digest(tag, expected):
            return header, None, "bad_tag"
        if not np.allclose(fp.compute(delta)["sketch"],
                           header["fp"]["sketch"]):
            return header, None, "fingerprint_mismatch"
    ''', "src/protocol.py · unpack", x=Inches(6.0), y=Inches(5.2), w=Inches(4.45),
               h=Inches(1.68), size_cap=9)
    rect(slide, Inches(10.6), Inches(5.2), Inches(2.18), Inches(1.68), fill=ACCENT_DIM,
         radius=0.08)
    text(slide, Inches(10.6), Inches(5.2), Inches(2.18), Inches(1.68),
         [[(f"{PG['global']['tamper_rejected']} / {PG['global']['tamper_sent']}",
            {"size": 26, "bold": True, "color": ACCENT, "font": DISPLAY})],
          [("tampered messages rejected", {"size": 11, "color": SOFT})]],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=1.05)
    notes(slide, """
        Step six runs on the server and follows this flowchart. The message is split into its
        four parts. Check one: the server recomputes the HMAC tag with that client's secret key.
        If it does not match, something changed on the way and the message is rejected as
        bad tag. Check two: the server recomputes the fingerprint from the payload itself. If it
        differs from the one in the header, the client tried to lie about its update, and the
        message is rejected. Only messages that pass both checks go on to scoring.
        The few lines of code at the bottom are these two checks. In our tests we changed one
        byte in 105 messages, and all 105 were rejected.
    """)


def s10_scoring(prs):
    slide = base(prs, mtag(7), "Anomaly scoring: is this update suspicious?",
                 "Three cheap scores, computed only from the fingerprints of this round's "
                 "updates.")
    cw, gap = Inches(3.93), Inches(0.22)
    cards = [
        ("Norm score", "Is it much bigger or smaller than the others?",
         "| log( size / median size ) |"),
        ("Consensus score", "Does it point away from everyone else?",
         "1 − cos( sketch, median sketch )"),
        ("History score", "Is it unlike this client's own last update?",
         "1 − cos( sketch, last sketch )"),
    ]
    for i, (t, q, f) in enumerate(cards):
        x = LEFT + i * (cw + gap)
        rect(slide, x, Inches(1.85), cw, Inches(3.55), fill=PANEL, radius=0.04)
        text(slide, x + Inches(0.25), Inches(1.98), cw - Inches(0.5), Inches(0.7),
             [[(t, {"bold": True, "size": 15})], [(q, {"size": 11, "color": SOFT})]],
             spacing=1.05)
        ox, oy = x + (Inches(1.7) if i == 1 else Inches(0.9)), Inches(4.3)
        if i == 0:
            for k, (ln, ang) in enumerate(((0.95, 55), (1.05, 40), (0.95, 25), (1.0, 10))):
                vec(slide, ox, oy, Inches(ln), ang, color=ACCENT)
            vec(slide, ox, oy, Inches(1.55), 68, color=AMBER, weight=2.25)
            text(slide, ox + Inches(0.75), Inches(2.85), Inches(1.6), Inches(0.3),
                 "too large", size=10, color=AMBER, bold=True)
        elif i == 1:
            for ang in (28, 38, 46, 34):
                vec(slide, ox, oy, Inches(1.5), ang, color=MUTED, weight=1.25)
            vec(slide, ox, oy, Inches(1.9), 37, color=ACCENT, weight=2.5)
            text(slide, ox + Inches(1.55), Inches(2.95), Inches(1.0), Inches(0.3), "median",
                 size=10, color=ACCENT, bold=True)
            vec(slide, ox, oy, Inches(1.25), 150, color=AMBER, weight=2.25)
            text(slide, x + Inches(0.25), Inches(3.35), Inches(1.0), Inches(0.3), "outlier",
                 size=10, color=AMBER, bold=True)
        else:
            vec(slide, ox, oy, Inches(1.8), 35, color=MUTED, weight=2)
            text(slide, ox + Inches(1.55), Inches(3.05), Inches(1.4), Inches(0.3),
                 "last round", size=10, color=MUTED, bold=True)
            vec(slide, ox, oy, Inches(1.4), 105, color=AMBER, weight=2.25)
            text(slide, ox - Inches(0.75), Inches(3.3), Inches(0.65), Inches(0.5),
                 "this round", size=10, color=AMBER, bold=True)
        rect(slide, x + Inches(0.2), Inches(4.65), cw - Inches(0.4), Inches(0.5),
             fill=ACCENT_DIM, radius=0.2)
        text(slide, x + Inches(0.2), Inches(4.65), cw - Inches(0.4), Inches(0.5), f,
             size=11.5, color=ACCENT, bold=True, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE)
    rect(slide, LEFT, Inches(5.6), CONTENT_W, Inches(1.25), fill=PANEL, radius=0.06)
    rect(slide, LEFT, Inches(5.6), Inches(0.06), Inches(1.25), fill=AMBER)
    text(slide, LEFT + Inches(0.3), Inches(5.6), Inches(5.0), Inches(1.25), [
        [("Standardize within the round", {"bold": True, "size": 14})],
        [("z = (score − median) / (1.4826 × MAD)", {"size": 13, "color": ACCENT,
                                                    "bold": True})]],
         anchor=MSO_ANCHOR.MIDDLE, spacing=1.25)
    text(slide, Inches(5.8), Inches(5.6), Inches(6.8), Inches(1.25),
         "Each score is compared with the other clients in the same round. Lesson learned: "
         "our first version used fixed limits, and once training settled 65–96% of honest "
         "updates were flagged. Comparing within the round fixed it.",
         size=11.5, color=SOFT, anchor=MSO_ANCHOR.MIDDLE, spacing=1.15)
    notes(slide, """
        Step seven asks: does this update look suspicious? We use three cheap scores, all from
        the fingerprints, so the server never has to study the full update.
        First, the norm score: is this update much bigger or smaller than the others? In the
        picture, one arrow is far longer than the rest.
        Second, the consensus score: we take the median direction of all clients, the dark
        arrow, and measure how far each update points away from it. The median is used because
        a few attackers cannot drag it.
        Third, the history score: is this update very different from the same client's update
        last round?
        At the bottom: each score is standardized against the other clients in the same round.
        This was an important lesson. Our first version used fixed limits, and once training
        settled down it flagged 65 to 96 percent of honest updates.
    """)


def s11_threshold(prs):
    slide = base(prs, mtag(8), "Decision: threshold, second check, capped average",
                 "Rounds 1–5 are clean and set the limits. From round 6 every update goes "
                 "through this decision.")
    # Flowchart (left).
    x0 = LEFT
    box(slide, x0, Inches(1.95), Inches(2.4), Inches(0.75), "3 standardized scores")
    line(slide, x0 + Inches(1.2), Inches(2.7), x0 + Inches(1.2), Inches(2.95), color=ACCENT,
         head=True)
    diamond(slide, x0 - Inches(0.05), Inches(2.95), Inches(2.5), Inches(1.15),
            "Any score\nabove limit?")
    box(slide, x0 + Inches(3.3), Inches(3.15), Inches(2.0), Inches(0.75), "Accept",
        fill=ACCENT_DIM, line_c=ACCENT, title_color=ACCENT)
    line(slide, x0 + Inches(2.45), Inches(3.52), x0 + Inches(3.3), Inches(3.52),
         color=ACCENT, head=True)
    text(slide, x0 + Inches(2.6), Inches(3.2), Inches(0.5), Inches(0.25), "no", size=10,
         color=ACCENT, bold=True)
    line(slide, x0 + Inches(1.2), Inches(4.1), x0 + Inches(1.2), Inches(4.35), color=AMBER,
         head=True)
    text(slide, x0 + Inches(1.3), Inches(4.08), Inches(0.5), Inches(0.25), "yes", size=10,
         color=AMBER, bold=True)
    diamond(slide, x0 - Inches(0.05), Inches(4.35), Inches(2.5), Inches(1.15),
            "Close to\ntrimmed mean?")
    box(slide, x0 + Inches(3.3), Inches(4.55), Inches(2.0), Inches(0.75), "Rescue",
        "accept after all", fill=ACCENT_DIM, line_c=ACCENT, title_color=ACCENT)
    line(slide, x0 + Inches(2.45), Inches(4.92), x0 + Inches(3.3), Inches(4.92),
         color=ACCENT, head=True)
    text(slide, x0 + Inches(2.6), Inches(4.6), Inches(0.5), Inches(0.25), "yes", size=10,
         color=ACCENT, bold=True)
    line(slide, x0 + Inches(1.2), Inches(5.5), x0 + Inches(1.2), Inches(5.75), color=AMBER,
         head=True)
    box(slide, x0, Inches(5.75), Inches(2.4), Inches(0.7), "Reject", fill=AMBER_DIM,
        line_c=AMBER, title_color=AMBER)
    line(slide, x0 + Inches(5.3), Inches(3.52), x0 + Inches(5.65), Inches(3.52), color=ACCENT)
    line(slide, x0 + Inches(5.3), Inches(4.92), x0 + Inches(5.65), Inches(4.92), color=ACCENT)
    line(slide, x0 + Inches(5.65), Inches(3.52), x0 + Inches(5.65), Inches(5.75),
         color=ACCENT, head=True)
    box(slide, x0 + Inches(3.3), Inches(5.75), Inches(2.6), Inches(0.7), "Capped FedAvg",
        "no client above 15%", fill=ACCENT, line_c=ACCENT, title_color=PANEL,
        body_color=ACCENT_DIM)
    # fix the subtitle colour on the solid box
    # Global vs Mondrian (right).
    gx, gw = Inches(7.0), Inches(5.78)
    rect(slide, gx, Inches(1.85), gw, Inches(5.0), fill=PANEL, radius=0.04)
    label_caps(slide, gx + Inches(0.25), Inches(1.97), gw, "Where the limit comes from")
    text(slide, gx + Inches(0.25), Inches(2.3), gw - Inches(0.5), Inches(0.7),
         "Conformal threshold from the 5 clean rounds: about 5% of honest scores (alpha = "
         "0.05) are allowed above it.", size=11.5, color=SOFT, spacing=1.1)
    honest = [0.9, 1.4, 0.7, 2.6, 2.9, 1.1, 0.5, 2.4, 1.6, 3.0]
    clusters = [0, 0, 0, 1, 1, 0, 2, 1, 0, 1]
    for k, (title, mond) in enumerate((("Global: one limit for all", False),
                                       ("Mondrian: one limit per cluster", True))):
        py = Inches(3.15) + k * Inches(1.85)
        text(slide, gx + Inches(0.25), py, gw, Inches(0.3), title, size=12.5, bold=True)
        base_y, sx = py + Inches(1.45), gx + Inches(0.5)
        line(slide, sx - Inches(0.1), base_y, gx + gw - Inches(0.3), base_y, color=LINE)
        for i, v in enumerate(honest):
            x = sx + i * Inches(0.5)
            y = base_y - Inches(0.3 * v)
            col = [ACCENT, AMBER, FN][clusters[i]] if mond else ACCENT
            rect(slide, x, y - Inches(0.08), Inches(0.16), Inches(0.16), shape=MSO_SHAPE.OVAL,
                 fill=col)
        if not mond:
            ly = base_y - Inches(0.3 * 2.2)
            line(slide, sx - Inches(0.1), ly, gx + gw - Inches(0.3), ly, color=AMBER,
                 weight=1.5)
            text(slide, gx + gw - Inches(1.35), ly - Inches(0.28), Inches(1.1), Inches(0.25),
                 "limit", size=10, color=AMBER, bold=True, align=PP_ALIGN.RIGHT)
        else:
            for c, lv, colr in ((0, 1.85, ACCENT), (1, 3.25, AMBER), (2, 0.8, FN)):
                xs_ = [sx + i * Inches(0.5) for i in range(10) if clusters[i] == c]
                ly = base_y - Inches(0.3 * lv)
                line(slide, min(xs_) - Inches(0.08), ly, max(xs_) + Inches(0.24), ly,
                     color=colr, weight=1.5)
        text(slide, gx + gw - Inches(0.3) - Inches(0.1), base_y + Inches(0.02), Inches(0.3),
             Inches(0.2), "", size=8)
    text(slide, gx + Inches(0.25), Inches(6.45), gw - Inches(0.5), Inches(0.35),
         "Dots = honest clients' scores. In the global plot, unusual clients sit above the "
         "line.", size=10, color=MUTED)
    notes(slide, """
        Step eight makes the decision, following the flowchart on the left. If none of the
        three scores is above its limit, the update is accepted. If one is, it is not thrown
        away immediately: a second check compares it with a trimmed mean of all updates, which
        ignores the most extreme values. If it is close enough, it is rescued; otherwise it is
        rejected. All accepted updates are then averaged with FedAvg, but no client may hold
        more than 15 percent of the weight, so one big router cannot dominate.
        On the right is where the limit comes from. In the 5 clean rounds we collect scores and
        set a conformal threshold, so only about 5 percent of honest scores go above it. With a
        global threshold there is one line for everybody, and honest clients with unusual
        traffic can end up above it. With Mondrian, clients are grouped into 3 clusters by
        k-means and each cluster gets its own line. Which one is better is our research
        question, answered on slide 13.
    """)


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
