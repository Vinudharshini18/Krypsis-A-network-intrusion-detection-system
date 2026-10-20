"""
Builds Krypsis_Final_Review.pptx — the 18-slide final-review deck in a
clean, large-text style: introduction, objectives, seven methodology
slides, four code slides, two result slides with native charts, a
comparison table and the conclusion. Speaker notes on every slide.

Every number comes from results/*.json or the processed data.

Run: ..\\venv\\Scripts\\python.exe build_final_review.py
"""

import json
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
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(ROOT, "results")
OUT_PATH = os.path.join(HERE, "Krypsis_Final_Review.pptx")

WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x1E, 0x2A, 0x30)
GREY = RGBColor(0x5F, 0x6B, 0x73)
SOFT_GREY = RGBColor(0xA3, 0xAD, 0xB4)
LINE = RGBColor(0xD5, 0xDC, 0xE0)
CODE_BG = RGBColor(0xF3, 0xF5, 0xF6)
ACCENT = RGBColor(0x0F, 0x5F, 0x6B)
ACCENT_MID = RGBColor(0x7F, 0xB4, 0xBA)
ACCENT_LIGHT = RGBColor(0xE4, 0xF0, 0xF1)
STRING = RGBColor(0x8A, 0x5A, 0x00)

FONT = "Segoe UI"
TITLE_FONT = "Segoe UI Semibold"
MONO = "Consolas"

W, H = Inches(13.333), Inches(7.5)
LEFT = Inches(0.7)
CONTENT_W = Inches(11.93)

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


def p(x, d=1):
    return f"{100 * x:.{d}f}%"


# ------------------------------------------------------------------ helpers

def _e(*v):
    return [Emu(int(round(x))) for x in v]


def _runs(content):
    return [(content, {})]


def text(slide, x, y, w, h, content, size=20, color=INK, bold=False, font=FONT,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.15, italic=False):
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
        par.line_spacing = spacing
        runs = _runs(para) if isinstance(para, str) else para
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


def bullets(slide, x, y, w, h, items, size=20, gap=12, color=INK):
    box = slide.shapes.add_textbox(*_e(x, y, w, h))
    tf = box.text_frame
    tf.word_wrap = True
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    for i, item in enumerate(items):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.line_spacing = 1.1
        par.space_after = Pt(gap)
        pPr = par._p.get_or_add_pPr()
        ind = int(Inches(0.3))
        pPr.set("marL", str(ind))
        pPr.set("indent", str(-ind))
        clr = pPr.makeelement(qn("a:buClr"), {})
        clr.append(clr.makeelement(qn("a:srgbClr"), {"val": str(ACCENT)}))
        pPr.append(clr)
        pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
        pPr.append(pPr.makeelement(qn("a:buChar"), {"char": "•"}))
        lead, rest = item if isinstance(item, tuple) else (None, item)
        if lead:
            r = par.add_run()
            r.text = lead + " "
            r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), True, ACCENT, FONT
        for t, st in _runs(rest):
            r = par.add_run()
            r.text = t
            r.font.size, r.font.name = Pt(size), FONT
            r.font.color.rgb = st.get("color", color)
            r.font.bold = st.get("bold", False)
    return box


def rect(slide, x, y, w, h, fill=WHITE, line=LINE, radius=0.08, dashed=False, line_w=1.0):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                               *_e(x, y, w, h))
    if radius:
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
        if dashed:
            s.line.dash_style = 4  # dash
    return s


def box(slide, x, y, w, h, title, sub=None, fill=WHITE, line=LINE, title_color=INK,
        size=18, sub_size=16, dashed=False, sub_color=GREY):
    rect(slide, x, y, w, h, fill=fill, line=line, dashed=dashed)
    content = [[(title, {"bold": True, "color": title_color, "size": size})]]
    if sub:
        content.append([(sub, {"color": sub_color, "size": sub_size})])
    text(slide, x + Inches(0.1), y, w - Inches(0.2), h, content, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE, spacing=1.05)


def _plain(c):
    st = c._element.find(qn("p:style"))
    if st is not None:
        c._element.remove(st)
    return c


def line(slide, x1, y1, x2, y2, color=SOFT_GREY, weight=1.5, head=True):
    c = _plain(slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, *_e(x1, y1, x2, y2)))
    c.line.color.rgb = color
    c.line.width = Pt(weight)
    if head:
        ln = c.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def notes(slide, content):
    slide.notes_slide.notes_text_frame.text = textwrap.dedent(content).strip()


def base(prs, title=None, footer=True):
    """Every content slide: a small section label, the title, a hairline
    rule, and a quiet footer. "Section: Title" splits into the two."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _no[0] += 1
    rect(slide, 0, 0, W, H, fill=WHITE, line=None, radius=None)
    if title:
        section, _, heading = title.partition(": ")
        heading = heading[:1].upper() + heading[1:]
        text(slide, LEFT, Inches(0.38), CONTENT_W, Inches(0.3), section.upper(), size=16,
             bold=True, color=ACCENT)
        text(slide, LEFT, Inches(0.68), CONTENT_W, Inches(0.65), heading, size=34,
             font=TITLE_FONT, anchor=MSO_ANCHOR.MIDDLE)
        line(slide, LEFT, Inches(1.4), LEFT + CONTENT_W, Inches(1.4), color=LINE, weight=0.75,
             head=False)
    if footer:
        text(slide, LEFT, Inches(6.95), Inches(8), Inches(0.35),
             "Krypsis  ·  Federated Network Intrusion Detection", size=16, color=SOFT_GREY)
        text(slide, Inches(11.13), Inches(6.95), Inches(1.5), Inches(0.35), f"{_no[0]} / 18",
             size=16, color=SOFT_GREY, align=PP_ALIGN.RIGHT)
    return slide


# ------------------------------------------------------------------ charts

def bar_chart(slide, x, y, w, h, categories, series, colors, title=None, fmt='0.0"%"',
              vmin=None, vmax=None, legend=True, gap=80, label_fmt=None, unit=None):
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values)
    chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, *_e(x, y, w, h), data).chart
    chart.font.size = Pt(16)
    chart.font.name = FONT
    chart.font.color.rgb = INK
    chart.has_title = bool(title)
    if title:
        chart.chart_title.text_frame.text = title
        tp = chart.chart_title.text_frame.paragraphs[0]
        tp.runs[0].font.size = Pt(18)
        tp.runs[0].font.bold = True
        tp.runs[0].font.color.rgb = INK
    plot = chart.plots[0]
    plot.gap_width = gap
    plot.overlap = -10
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = label_fmt or fmt
    dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size = Pt(16)
    for s, c in zip(plot.series, colors):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = c
    va = chart.value_axis
    if vmin is not None:
        va.minimum_scale = vmin
    if vmax is not None:
        va.maximum_scale = vmax
    if unit is not None:
        va.major_unit = unit
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = LINE
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(16)
    va.tick_labels.font.color.rgb = GREY
    va.tick_labels.number_format = fmt
    va.tick_labels.number_format_is_linked = False
    ca = chart.category_axis
    ca.tick_labels.font.size = Pt(16)
    ca.format.line.color.rgb = LINE
    chart.has_legend = legend and len(series) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(16)
    return chart


# ------------------------------------------------------------------ code

KEYWORDS = {"def", "return", "for", "in", "if", "not", "or", "and", "class", "else",
            "None", "True", "False", "import", "from", "with", "as"}
_TOKEN = re.compile(r'(#.*$)|("[^"]*")|([A-Za-z_][A-Za-z_0-9]*)|(.)')


def _code_runs(line_):
    runs = []
    for m in _TOKEN.finditer(line_):
        comment, string, word, _ = m.groups()
        if comment:
            runs.append((comment, {"color": GREY, "italic": True}))
        elif string:
            runs.append((string, {"color": STRING}))
        elif word in KEYWORDS:
            runs.append((word, {"color": ACCENT, "bold": True}))
        else:
            runs.append((m.group(0), {}))
    return runs or [(" ", {})]


def code_slide(prs, title, filename, source, points, note):
    slide = base(prs, title)
    x, y, w, h = LEFT, Inches(1.55), Inches(8.55), Inches(5.2)
    rect(slide, x, y, w, h, fill=CODE_BG, line=None, radius=0.03)
    text(slide, x + Inches(0.3), y + Inches(0.15), w - Inches(0.5), Inches(0.35), filename,
         size=16, color=GREY, font=MONO)
    lines = textwrap.dedent(source).strip("\n").split("\n")
    assert max(len(l) for l in lines) <= 64, (title, max(lines, key=len))
    text(slide, x + Inches(0.3), y + Inches(0.65), w - Inches(0.4), h - Inches(0.75),
         [_code_runs(l) for l in lines], size=16, font=MONO, spacing=1.0)
    rx = Inches(9.6)
    text(slide, rx, Inches(1.6), Inches(3.03), Inches(0.4), "What this code does", size=20,
         bold=True, color=ACCENT)
    bullets(slide, rx, Inches(2.2), Inches(3.03), Inches(4.5), points, size=18, gap=14)
    notes(slide, note)
    return slide


# ------------------------------------------------------------------ slides

def s1_title(prs):
    slide = base(prs, footer=False)
    rect(slide, 0, 0, Inches(4.3), H, fill=ACCENT, line=None, radius=None)
    text(slide, Inches(0.7), Inches(0.9), Inches(3.2), Inches(1.2),
         "COMPUTER NETWORKS\nFinal Project Review", size=18, color=WHITE, spacing=1.4)
    line(slide, Inches(0.7), Inches(6.35), Inches(1.7), Inches(6.35), color=WHITE, weight=1.5,
         head=False)
    x = Inches(5.0)
    text(slide, x, Inches(1.25), Inches(7.8), Inches(1.3), "Krypsis", size=66,
         font=TITLE_FONT, color=ACCENT)
    text(slide, x, Inches(2.55), Inches(7.6), Inches(1.1),
         "Federated network intrusion detection\nwith a secure update protocol",
         size=24, color=INK, spacing=1.2)
    line(slide, x, Inches(3.95), x + Inches(1.2), Inches(3.95), color=ACCENT, weight=2,
         head=False)
    text(slide, x, Inches(4.3), Inches(7), Inches(0.4), "TEAM", size=16, bold=True,
         color=GREY)
    team = [("Rithika K", "CB.SC.U4AIE25126"), ("Pradhaniya S", "CB.SC.U4AIE25148"),
            ("Sathya K", "CB.SC.U4AIE25154"), ("Vinudharshini PP", "CB.SC.U4AIE25161")]
    for i, (name, roll) in enumerate(team):
        col, row = i % 2, i // 2
        text(slide, x + col * Inches(3.7), Inches(4.8) + row * Inches(0.95), Inches(3.5),
             Inches(0.9), [[(name, {"bold": True, "size": 20})],
                           [(roll, {"size": 16, "color": GREY})]], spacing=1.1)
    notes(slide, """
        Good morning. Our project is called Krypsis.
        It is a network intrusion detection system that learns from many routers
        without collecting their traffic in one place. This is called federated learning.
        On top of that, we designed our own protocol that checks every model update
        before the server uses it.
    """)


def s2_intro(prs):
    slide = base(prs, "Introduction: why federated intrusion detection?")
    bullets(slide, LEFT, Inches(1.7), Inches(6.4), Inches(5), [
        ("Intrusion detection:", "spotting attacks inside network traffic."),
        ("Federated learning:", "data stays on each device; only model updates are shared."),
        ("The risk:", "a bad client can send poisoned updates."),
        ("Our idea:", "check every update before the server uses it."),
    ], size=22, gap=20)
    # Diagram: server with three clients, one of them bad.
    cx = Inches(9.9)
    box(slide, cx - Inches(1.35), Inches(1.75), Inches(2.7), Inches(0.95), "Server",
        "combines updates", fill=ACCENT_LIGHT, line=ACCENT, title_color=ACCENT)
    clients = [("Client 1", "honest", False), ("Client 2", "honest", False),
               ("Client 3", "bad", True)]
    bw = Inches(1.55)
    for i, (name, kind, bad) in enumerate(clients):
        x = Inches(7.65) + i * Inches(1.75)
        y = Inches(4.3)
        box(slide, x, y, bw, Inches(1.0), name, kind, fill=WHITE,
            line=INK if bad else LINE, dashed=bad, title_color=INK,
            sub_color=INK if bad else GREY)
        line(slide, x + bw / 2, y, cx + (i - 1) * Inches(0.6), Inches(2.7),
             color=INK if bad else ACCENT, weight=2 if bad else 1.5)
    text(slide, Inches(7.65), Inches(5.55), Inches(5.0), Inches(0.9),
         "Traffic stays with each client.\nOnly the model update travels.",
         size=16, color=GREY, align=PP_ALIGN.CENTER)
    notes(slide, """
        First, what is intrusion detection? It means looking at network traffic and
        deciding if it is normal or an attack.
        To learn this well, a model needs traffic from many places. But companies cannot
        share their traffic, because it is private.
        Federated learning solves this. Each device trains the model on its own data and
        only sends the model update, which is just a list of numbers, to the server.
        The server combines the updates into one shared model.
        But there is a new risk, shown as the dashed client on the right. A bad client can
        send a poisoned update and spoil the shared model.
        So our idea is simple: check every update before the server uses it.
    """)


def s3_objectives(prs):
    slide = base(prs, "Objectives: what we set out to do")
    objs = [
        "Detect network attacks without sharing raw data",
        "Protect training from poisoned or fake client updates",
        "Design our own secure communication protocol",
        "Check if one global threshold unfairly flags honest clients",
        "Compare global vs per-cluster (Mondrian) thresholds",
    ]
    for i, o in enumerate(objs):
        y = Inches(1.75) + i * Inches(1.0)
        rect(slide, LEFT, y, Inches(0.7), Inches(0.7), fill=ACCENT_LIGHT, line=None, radius=0.5)
        text(slide, LEFT, y, Inches(0.7), Inches(0.7), str(i + 1), size=22, bold=True,
             color=ACCENT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, LEFT + Inches(1.0), y, Inches(10.5), Inches(0.7), o, size=24,
             anchor=MSO_ANCHOR.MIDDLE)
    notes(slide, """
        We had five objectives.
        One: build an attack detector where no one shares their raw traffic.
        Two: protect the training from clients that send poisoned or fake updates.
        Three: design our own protocol for sending updates safely.
        Four: our research question. Clients have different traffic, so an honest client
        can look unusual. We check whether one single threshold for everyone wrongly
        flags these honest clients.
        Five: compare that single global threshold with a Mondrian threshold, which means
        one threshold for each group of similar clients.
    """)


def s4_pipeline(prs):
    slide = base(prs, "Methodology: overall pipeline")
    bw, bh, gap = Inches(2.6), Inches(1.25), Inches(0.5)
    x0 = LEFT + Inches(0.1)
    xs = [x0 + i * (bw + gap) for i in range(4)]
    y1, y2 = Inches(1.85), Inches(3.9)
    row1 = [("Dataset", "FLNET2023, 10 routers"), ("Preprocessing", "clean and scale"),
            ("Split to clients", "1 router = 1 client"), ("Local training", "each client trains")]
    for i, (t, s) in enumerate(row1):
        box(slide, xs[i], y1, bw, bh, t, s, size=20)
        if i < 3:
            line(slide, xs[i] + bw, y1 + bh / 2, xs[i + 1], y1 + bh / 2, color=ACCENT)
    line(slide, xs[3] + bw / 2, y1 + bh, xs[3] + bw / 2, y2, color=ACCENT)
    row2 = [(3, "Protocol check", "tag + fingerprint", True),
            (2, "Server aggregation", "FedAvg average", False),
            (1, "Global model", "better every round", False)]
    for k, (col, t, s, ours) in enumerate(row2):
        box(slide, xs[col], y2, bw, bh, t, s, size=20,
            fill=ACCENT_LIGHT if ours else WHITE, line=ACCENT if ours else LINE,
            title_color=ACCENT if ours else INK)
        if k < 2:
            line(slide, xs[col], y2 + bh / 2, xs[col - 1] + bw, y2 + bh / 2, color=ACCENT)
    # loop back: global model -> local training (next round)
    ly = y2 + bh + Inches(0.4)
    gx = xs[1] + bw / 2
    tx = xs[3] + bw + Inches(0.25)
    line(slide, gx, y2 + bh, gx, ly, color=SOFT_GREY, head=False)
    line(slide, gx, ly, tx, ly, color=SOFT_GREY, head=False)
    line(slide, tx, ly, tx, y1 + bh / 2, color=SOFT_GREY, head=False)
    line(slide, tx, y1 + bh / 2, xs[3] + bw, y1 + bh / 2, color=SOFT_GREY)
    text(slide, xs[1] + bw / 2 + Inches(0.2), ly + Inches(0.08), Inches(6), Inches(0.4),
         "sent back to clients for the next round", size=16, color=GREY)
    text(slide, xs[0], y2 + Inches(0.15), bw, Inches(1.0),
         "Highlighted box = our protocol", size=16, color=ACCENT)
    notes(slide, """
        This is the whole system in one picture.
        We start with the FLNET2023 dataset, which has traffic from 10 routers.
        We clean and scale the data. Then we give each router's data to one client, so we have
        10 clients.
        Each client trains the model on its own data. Then the update goes through our protocol
        check, the highlighted box. Only updates that pass are averaged by the server. This
        is called FedAvg.
        The result is the new global model. It is sent back to the clients and the loop repeats
        for the next round.
    """)


def s5_data(prs):
    slide = base(prs, "Methodology: dataset and preprocessing")
    text(slide, LEFT, Inches(1.6), Inches(5.6), Inches(0.5), "Dataset: FLNET2023", size=22,
         bold=True, color=ACCENT)
    bullets(slide, LEFT, Inches(2.2), Inches(5.6), Inches(4.6), [
        "Network traffic recorded at 10 routers",
        "564,007 training flows, 79,491 test flows",
        "66 features per flow: packets, bytes, timing",
        "Label: Normal (34%) or Attack (66%, 10 types)",
        "NSL-KDD used as a second dataset",
    ], size=20, gap=14)
    steps = [("Take a 10% sample of each file", "4.8 M flows is too many to train often"),
             ("Remove IP, port and timestamp", "learn behaviour, not addresses"),
             ("Remove broken rows and constant columns", "inf / empty values, no information"),
             ("Log scale, then scale to 0–1", "fitted on training data only")]
    x, w, h = Inches(6.75), Inches(5.85), Inches(1.0)
    text(slide, x, Inches(1.6), w, Inches(0.5), "Preprocessing steps", size=22, bold=True,
         color=ACCENT)
    for i, (t, why) in enumerate(steps):
        y = Inches(2.2) + i * Inches(1.18)
        box(slide, x, y, w, h, t, "why: " + why, size=18)
        if i < 3:
            line(slide, x + w / 2, y + h, x + w / 2, y + Inches(1.18), color=ACCENT)
    notes(slide, """
        Our main dataset is FLNET2023. It was made for federated learning research. Traffic was
        recorded at 10 routers in a network.
        Each row is one flow, which means one conversation between two machines. Each flow has
        66 features, like number of packets, bytes and timing.
        The label is normal or attack. About 66 percent of training flows are attacks, of 10
        different types like DDoS, DoS, web attacks and man-in-the-middle.
        Preprocessing has four steps. First, we take a 10 percent sample of each file, because
        the full data is 4.8 million flows, too big to train many times on a laptop.
        Second, we remove IP addresses, port and time. Otherwise the model would just learn the
        attacker's address instead of what an attack looks like.
        Third, we remove broken rows and columns that never change.
        Fourth, we use a log scale and then scale every value to between 0 and 1. The scaler is
        fitted on training data only, so the test data stays unseen.
        We also repeat our tests on NSL-KDD, a well-known older dataset.
    """)


def s6_clients(prs):
    slide = base(prs, "Methodology: client simulation (IID vs non-IID)")
    bullets(slide, LEFT, Inches(1.65), Inches(4.6), Inches(5.2), [
        ("IID:", "every client gets a similar mix of data."),
        ("Non-IID:", "each client's data is different."),
        ("FLNET2023:", "each real router is one client."),
        ("NSL-KDD:", "uneven clients made with a Dirichlet split."),
        ("Why:", "real networks are uneven, so this matters."),
    ], size=19, gap=12)
    iid = [66.0, 66.3, 65.7, 65.6, 65.8, 65.8, 66.3, 65.6, 66.1, 66.1]
    router = [55.7, 83.2, 19.0, 92.1, 76.3, 66.1, 42.2, 50.8, 72.3, 68.5]
    dirichlet = [28.0, 100.0, 99.2, 18.4, 40.2, 97.6, 40.2, 11.9, 84.1, 54.3]
    bar_chart(slide, Inches(5.55), Inches(1.5), Inches(7.1), Inches(5.3),
              [str(i) for i in range(1, 11)],
              [("IID split", iid), ("Real routers (FLNET2023)", router),
               ("Dirichlet split (NSL-KDD)", dirichlet)],
              [SOFT_GREY, ACCENT, ACCENT_MID], title="Attack % in each client's data",
              fmt='0"%"', vmin=0, vmax=100, gap=60).plots[0].has_data_labels = False
    notes(slide, """
        In federated learning, we must decide how the data is spread over the clients.
        IID means every client gets a similar mix. In the chart, the grey bars are flat:
        every client has about 66 percent attack traffic.
        Non-IID means each client's data is different. This is how real networks are.
        For FLNET2023 we did not need to fake this. Each real router is one client. The dark bars
        show that router 3 has only 19 percent attacks, while router 4 has 92 percent.
        For NSL-KDD we created uneven clients with a Dirichlet split. A Dirichlet split gives each
        client a random share of each attack type. We used alpha equal to 0.5. A smaller alpha
        makes the clients more uneven. The light bars show it: some clients are almost all
        attack, others almost all normal.
        This matters because an honest client with unusual data can look suspicious. That is
        exactly our research question.
    """)


def s7_model(prs):
    slide = base(prs, "Methodology: model and federated training")
    layers = [("Input", "66 features"), ("Dense 256", "ReLU + dropout"),
              ("Dense 128", "ReLU + dropout"), ("Dense 64", "ReLU + dropout"),
              ("Output", "normal / attack")]
    bw, gap = Inches(2.05), Inches(0.42)
    for i, (t, s) in enumerate(layers):
        x = LEFT + i * (bw + gap)
        box(slide, x, Inches(1.6), bw, Inches(1.0), t, s, size=19,
            fill=ACCENT_LIGHT if 0 < i < 4 else WHITE, line=ACCENT if 0 < i < 4 else LINE)
        if i < 4:
            line(slide, x + bw, Inches(2.1), x + bw + gap, Inches(2.1), color=ACCENT)
    # FedAvg loop, 2 x 2
    cw, ch = Inches(2.9), Inches(1.05)
    gx = [LEFT, LEFT + Inches(3.75)]
    gy = [Inches(3.25), Inches(5.3)]
    cells = [(0, 0, "1. Server sends model"), (1, 0, "2. Clients train locally"),
             (1, 1, "3. Clients send updates"), (0, 1, "4. Server averages")]
    for c, r, t in cells:
        box(slide, gx[c], gy[r], cw, ch, t, size=18)
    line(slide, gx[0] + cw, gy[0] + ch / 2, gx[1], gy[0] + ch / 2, color=ACCENT)
    line(slide, gx[1] + cw / 2, gy[0] + ch, gx[1] + cw / 2, gy[1], color=ACCENT)
    line(slide, gx[1], gy[1] + ch / 2, gx[0] + cw, gy[1] + ch / 2, color=ACCENT)
    line(slide, gx[0] + cw / 2, gy[1], gx[0] + cw / 2, gy[0] + ch, color=ACCENT)
    text(slide, gx[0] + Inches(1.55), Inches(4.55), Inches(3.6), Inches(0.4),
         "repeat every round", size=16, color=GREY, align=PP_ALIGN.CENTER)
    bullets(slide, Inches(7.9), Inches(3.3), Inches(4.75), Inches(3.5), [
        ("FedAvg:", "average of client models, weighted by data size."),
        ("Training:", "15 rounds, 2 local passes per round."),
        ("Baseline:", "same model trained on all data together."),
        "The baseline shows the best accuracy to aim for.",
    ], size=19, gap=12)
    notes(slide, """
        Our model is a simple neural network called an MLP, a multilayer perceptron.
        It takes the 66 features, passes them through three layers of 256, 128 and 64 neurons,
        and outputs one number: normal or attack. Dropout randomly switches off some neurons while
        training, which stops the model from memorising.
        Federated training works in a loop, shown at the bottom. The server sends the model. Each
        client trains it on its own data. The clients send back their updates. The server averages
        them. This averaging is called FedAvg. A client with more data gets more weight.
        We run 15 rounds, and each client trains for 2 passes over its data per round.
        For comparison, we also train the same model the normal way, with all data in one place.
        This is the centralized baseline. It tells us the best accuracy we can hope for.
    """)


def s8_protocol(prs):
    slide = base(prs, "Methodology: our protocol (Krypsis message)")
    parts = [("Header + fingerprint", "≈1.5 KB", Inches(3.9), ACCENT_LIGHT, ACCENT),
             ("Model update", f"{COMM['raw_payload_bytes'] / 1000:.0f} KB", Inches(5.2),
              WHITE, LINE),
             ("Integrity tag", "32 bytes", Inches(2.83), ACCENT_LIGHT, ACCENT)]
    x = LEFT
    for t, s, w, fill, ln in parts:
        box(slide, x, Inches(1.6), w, Inches(1.1), t, s, fill=fill, line=ln, size=20,
            title_color=ACCENT if fill == ACCENT_LIGHT else INK)
        x += w
    text(slide, LEFT, Inches(2.8), CONTENT_W, Inches(0.4), "One message sent by a client each round",
         size=16, color=GREY, align=PP_ALIGN.CENTER)
    cards = [
        ("Integrity tag", ["HMAC-SHA256 with each client's secret key",
                           "Proves the update was not changed on the way",
                           "One changed byte → message rejected"]),
        ("Anomaly fingerprint", ["Short summary: update size + 64-number sketch",
                                 "Server recomputes it, so it cannot be faked",
                                 "Gives scores: does this update look suspicious?"]),
    ]
    for i, (t, items) in enumerate(cards):
        cx = LEFT + i * Inches(6.07)
        rect(slide, cx, Inches(3.4), Inches(5.86), Inches(2.75), fill=WHITE, line=LINE)
        text(slide, cx + Inches(0.3), Inches(3.55), Inches(5.3), Inches(0.5), t, size=22,
             bold=True, color=ACCENT)
        bullets(slide, cx + Inches(0.3), Inches(4.15), Inches(5.35), Inches(2.0), items,
                size=18, gap=8)
    text(slide, LEFT, Inches(6.3), CONTENT_W, Inches(0.45),
         f"Extra cost: only +{p(COMM['krypsis_overhead_bytes'] / COMM['raw_payload_bytes'], 2)} "
         f"message size. Plain JSON would be "
         f"{COMM['http_json_bytes'] / COMM['raw_payload_bytes']:.1f}× bigger.",
         size=18, color=INK, align=PP_ALIGN.CENTER)
    notes(slide, """
        This is the most important part: our own protocol.
        Every round, each client sends one message with three parts. The model update in the
        middle is the actual list of numbers, about 233 kilobytes.
        On the right is the integrity tag. It is an HMAC, a kind of digital seal made with a
        secret key that only that client and the server know. If anyone changes even one byte on
        the way, the seal does not match and the server rejects the message.
        On the left is the header with the fingerprint. The fingerprint is a short summary of the
        update: how big it is, and a 64-number sketch of its direction. The server recalculates the
        fingerprint itself, so a client cannot lie about it.
        From the fingerprint the server computes three scores: is the update unusually big or
        small, does it point away from the other clients, and does it differ from this client's
        last update. High scores mean suspicious.
        All this protection makes the message only 0.67 percent bigger. Sending the same update
        as plain JSON text would be 5.6 times bigger.
    """)


def s9_attack(prs):
    slide = base(prs, "Methodology: attack simulation (label flipping)")
    text(slide, LEFT, Inches(1.6), Inches(5.6), Inches(0.5), "What a malicious client does",
         size=22, bold=True, color=ACCENT)
    rows = [("Attack flow", "trained as Normal"), ("Normal flow", "trained as Attack")]
    for i, (a, b) in enumerate(rows):
        y = Inches(2.35) + i * Inches(1.45)
        box(slide, LEFT, y, Inches(2.3), Inches(1.0), a, "true label", size=19)
        line(slide, LEFT + Inches(2.3), y + Inches(0.5), LEFT + Inches(3.1), y + Inches(0.5),
             color=INK, weight=2)
        box(slide, LEFT + Inches(3.1), y, Inches(2.5), Inches(1.0), b, "wrong label",
            size=19, dashed=True, line=INK)
    text(slide, LEFT, Inches(5.3), Inches(5.6), Inches(1.2),
         "The poisoned update teaches the shared model the opposite of the truth.",
         size=18, color=GREY)
    bullets(slide, Inches(6.9), Inches(1.7), Inches(5.75), Inches(5.0), [
        "2 of 10 clients are malicious, chosen randomly",
        "They flip labels: attack ↔ normal",
        "Rounds 1–5 are clean; attack starts round 6",
        "12 rounds per run, repeated with 5–15 seeds",
        "Also: 105 messages changed on the way",
    ], size=20, gap=16)
    notes(slide, """
        To test our protocol, we attack our own system.
        We use label flipping. A malicious client takes its own data and swaps the labels:
        attack flows are called normal, and normal flows are called attack. It trains on this
        wrong data and sends the update. This pulls the shared model in the wrong direction.
        In every run, 2 of the 10 clients are malicious. Which two is chosen randomly for each run.
        The first 5 rounds are clean. The server uses them to learn what normal updates look like
        and to set its thresholds. The attack starts in round 6. Each run is 12 rounds.
        We repeat every test with different random seeds, 15 seeds in the main protocol test,
        so the result is not just luck.
        We also test tampering: we changed one byte in 105 honest messages on the way to the server.
        We also tried a backdoor attack, which is in our report.
    """)


def s10_before_after(prs):
    slide = base(prs, "Methodology: before vs after the protocol")
    lx, bx = LEFT, Inches(2.75)
    lanes = [
        ("Without protocol", Inches(1.6), [("Clients", "incl. bad ones"), ("Average", "everything"),
                                         ("Poisoned model", None)], Inches(2.9)),
        ("With Krypsis", Inches(3.05), [("Clients", None), ("Check tag", "changed? reject"),
                                      ("Score fingerprint", "suspicious?"),
                                      ("Reject or down-weight", None),
                                      ("Safe average", None)], Inches(1.78)),
    ]
    for name, y, steps, bw in lanes:
        text(slide, lx, y, Inches(1.95), Inches(1.05), name, size=19, bold=True,
             color=ACCENT if "Krypsis" in name else GREY, anchor=MSO_ANCHOR.MIDDLE)
        gap = (Inches(9.88) - len(steps) * bw) / (len(steps) - 1)
        for i, (t, s) in enumerate(steps):
            x = bx + i * (bw + gap)
            ours = "Krypsis" in name and 0 < i < 4
            box(slide, x, y, bw, Inches(1.05), t, s, size=17, sub_size=16,
                fill=ACCENT_LIGHT if ours else WHITE, line=ACCENT if ours else LINE,
                title_color=ACCENT if ours else INK)
            if i < len(steps) - 1:
                line(slide, x + bw, y + Inches(0.52), x + bw + gap, y + Inches(0.52),
                     color=ACCENT if "Krypsis" in name else SOFT_GREY)
    line(slide, LEFT, Inches(4.4), LEFT + CONTENT_W, Inches(4.4), color=LINE, weight=1,
         head=False)
    text(slide, LEFT, Inches(4.55), CONTENT_W, Inches(0.5),
         "The threshold problem: how high must a score be to flag an update?",
         size=20, bold=True, color=ACCENT)
    cards = [("Global threshold", "one limit for all clients"),
             ("Mondrian threshold", "one limit per group of similar clients")]
    for i, (t, s) in enumerate(cards):
        box(slide, LEFT + i * Inches(3.55), Inches(5.2), Inches(3.35), Inches(1.15), t, s,
            size=19)
    text(slide, Inches(7.95), Inches(5.2), Inches(4.7), Inches(1.2),
         "Worry: honest clients with unusual (non-IID) data may cross one global limit.",
         size=18, color=INK, anchor=MSO_ANCHOR.MIDDLE)
    notes(slide, """
        Here is the difference our protocol makes.
        At the top, without protection, every update goes straight into the average, including
        the bad ones. So the model gets poisoned.
        Below, with Krypsis, the server first checks the integrity tag. If the message was
        changed, it is rejected. Then it scores the fingerprint. If the score is too high, the
        update is flagged. A flagged update gets a second check against a robust average. If it
        still looks bad, it is rejected. Also, no client can have more than 15 percent weight in
        the average. That is the down-weighting. Only then the server averages.
        But this raises a question: how high must a score be to flag an update? That limit is
        the threshold. We set it from the first 5 clean rounds so that only about 5 percent of
        honest updates would cross it.
        With a global threshold, there is one limit for everyone. With a Mondrian threshold, the
        server groups similar clients into 3 clusters and gives each group its own limit.
        Our worry was that honest clients with unusual data, the non-IID ones, would be wrongly
        flagged by one global limit. Mondrian should be fairer to them. We tested whether it is.
    """)


def s11_code_dirichlet(prs):
    code_slide(prs, "Code: Dirichlet non-IID split", "src/preprocess_nslkdd.py", '''
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
    ''', [
        "Takes each attack type one by one",
        "Draws random shares for the 10 clients",
        "Smaller alpha = more uneven clients (we use 0.5)",
        "Returns a client number for every row",
    ], """
        This code makes the uneven, non-IID clients for NSL-KDD.
        It goes through each attack type one at a time. For each type, it shuffles the rows and
        then asks the Dirichlet distribution for 10 random shares that add up to one. One share per
        client. So one client may get 70 percent of an attack type and another almost nothing.
        Alpha controls how uneven it is. We used 0.5, which gives quite uneven clients.
        The last line of the loop gives every row a client number. For FLNET2023 we did not need
        this, because the real routers are already uneven.
    """)


def s12_code_fedavg(prs):
    code_slide(prs, "Code: FedAvg aggregation", "src/federated_training.py", '''
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
            for client_id in range(num_clients):
                local_model.set_weights(global_weights)
                local_model.fit(X_client, y_client, epochs=2)
                ...
            global_weights = federated_average(local_weights, counts)
    ''', [
        "Each client starts from the global model",
        "Trains on its own data only",
        "Server averages every layer",
        "Clients with more data count more",
    ], """
        This is FedAvg, the heart of federated learning.
        Look at the loop at the bottom first. In every round, each client copies the global
        model, trains it for 2 passes on its own data, and keeps its new weights.
        Then federated_average combines them. For each layer of the network, it multiplies each
        client's weights by that client's share of the data and adds them up. So a client with
        twice as much data counts twice as much.
        The result becomes the new global model for the next round.
        In the protocol version, only updates that passed our checks are averaged.
    """)


def s13_code_protocol(prs):
    code_slide(prs, "Code: integrity tag and fingerprint", "src/protocol.py", '''
        # client: build the message
        fp = fingerprinter.compute(delta)  # size + 64-number sketch
        header = json.dumps({"client": client_id, "round": rnd,
                             "n": num_samples, "fp": fp}).encode()
        payload = delta.astype(np.float32).tobytes()
        tag = hmac.new(key, header + payload, hashlib.sha256).digest()

        # server: verify before using it
        expected = hmac.new(key, header + payload,
                            hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            return header, None, "bad_tag"
        actual = fingerprinter.compute(delta)
        if not np.allclose(actual["sketch"], claimed["sketch"]):
            return header, None, "fingerprint_mismatch"
    ''', [
        "Client seals header + update with its key",
        "Server rebuilds the seal and compares",
        "Server recomputes the fingerprint too",
        "Any mismatch → message rejected",
    ], """
        This is our protocol in code. The top half runs on the client.
        It computes the fingerprint of the update, puts it in the header with the client
        number and round, turns the update into bytes, and makes the HMAC tag using the client's
        secret key.
        The bottom half runs on the server. It makes the tag again with the same key. If the two
        tags are not the same, the message was changed, and it is rejected with bad_tag.
        Then it recomputes the fingerprint from the update itself. If it does not match what
        the client claimed, the message is rejected too. So a client cannot hide a bad update
        behind a nice-looking fingerprint.
        The code is slightly shortened to fit; the full version is in src/protocol.py.
    """)


def s14_code_threshold(prs):
    code_slide(prs, "Code: threshold check (global vs Mondrian)", "src/protocol.py", '''
        def conformal_threshold(scores, alpha):    # alpha = 0.05
            rank = math.ceil((len(scores) + 1) * (1 - alpha))
            return float(np.sort(scores)[rank - 1])

        class GlobalCalibrator:          # one limit for everyone
            def threshold_for(self, client):
                return self.thresholds

        class MondrianCalibrator:        # one limit per cluster
            def fit(self):
                labels = KMeans(n_clusters=k, ...).fit_predict(prof)
                ...
            def threshold_for(self, client):
                return self.thresholds[self.cluster_of[client]]

        def is_flagged(scores, thresholds):
            return any(scores[s] > thresholds[s] for s in SCORE_NAMES)
    ''', [
        "Limit set from 5 clean rounds",
        "Only ~5% of honest scores cross it",
        "Global: same limit for all clients",
        "Mondrian: limit for the client's cluster",
    ], """
        This code decides when an update is suspicious.
        conformal_threshold looks at the scores from the 5 clean calibration rounds and picks a
        limit so that only about 5 percent of honest updates would go above it. Alpha is 0.05.
        The global calibrator gives the same limit to every client.
        The Mondrian calibrator first groups the clients into 3 clusters with k-means, based on
        how their updates look. Then each cluster gets its own limit, and threshold_for returns
        the limit of that client's cluster.
        Finally is_flagged says: if any of the three scores is above its limit, flag the update.
        Some lines are shortened with dots to fit the slide.
    """)


def s15_accuracy(prs):
    slide = base(prs, "Results: accuracy without attack")
    cats = ["Centralized", "FedAvg IID", "FedAvg non-IID"]
    bar_chart(slide, LEFT, Inches(1.5), Inches(5.9), Inches(4.5), cats,
              [("Accuracy", [100 * CENTRAL["accuracy"], 100 * FED_IID["accuracy"],
                             100 * FED_ROUTER["accuracy"]])],
              [ACCENT], title="Normal vs attack: accuracy", fmt='0.00"%"', vmin=99.8,
              vmax=100.05, label_fmt='0.000"%"', unit=0.05)
    bar_chart(slide, Inches(6.8), Inches(1.5), Inches(5.85), Inches(4.5), cats,
              [("Macro-F1", [MC["centralized"]["macro_f1"], MC["federated_iid"]["macro_f1"],
                             MC["federated_router"]["macro_f1"]])],
              [ACCENT_MID], title="Naming the attack type: macro-F1", fmt="0.00",
              vmin=0, vmax=1)
    text(slide, LEFT, Inches(6.1), CONTENT_W, Inches(0.7),
         "Left axis starts at 99.8%. Federated nearly matches centralized; uneven data "
         "hurts the harder 11-type task.", size=18, color=GREY, align=PP_ALIGN.CENTER)
    notes(slide, f"""
        These results are on the FLNET2023 test set, with no attack.
        Left chart: normal-versus-attack accuracy. The centralized model scores
        {p(CENTRAL['accuracy'])}. Federated learning with an even IID split scores
        {p(FED_IID['accuracy'], 3)}, and with the real uneven routers {p(FED_ROUTER['accuracy'], 2)}.
        So keeping data private costs almost nothing. Please note the axis starts at 99.8 percent,
        so the small difference is visible.
        We checked why it is so high: one single feature, forward packet count, already gives
        97.5 percent. This dataset's binary task is easy.
        So we also trained the model to name the exact attack type, 11 classes. Right chart:
        macro-F1, which is the average score over all types. Centralized
        {MC['centralized']['macro_f1']:.2f}, IID {MC['federated_iid']['macro_f1']:.2f}, but real
        routers only {MC['federated_router']['macro_f1']:.2f}. Attack types that only one router
        sees get averaged away. That is the real cost of uneven data.
    """)


def s16_attack(prs):
    slide = base(prs, "Results: under label-flipping attack")
    fl, nl = DEF["flnet/label_flip"], DEF["nslkdd/label_flip"]
    cats = ["FLNET2023", "NSL-KDD"]
    bar_chart(slide, LEFT, Inches(1.5), Inches(5.9), Inches(4.6), cats,
              [("No protocol", [100 * fl["none"]["accuracy_mean"], 100 * nl["none"]["accuracy_mean"]]),
               ("With Krypsis", [100 * fl["v2"]["accuracy_mean"], 100 * nl["v2"]["accuracy_mean"]])],
              [SOFT_GREY, ACCENT], title="Accuracy under attack", fmt='0"%"', vmin=0,
              vmax=110, unit=20, label_fmt='0.0"%"')
    bar_chart(slide, Inches(6.8), Inches(1.5), Inches(5.85), Inches(4.6), cats,
              [("Attacks caught", [100 * fl["v2"]["detection_rate_mean"],
                                   100 * nl["v2"]["detection_rate_mean"]]),
               ("Honest wrongly flagged", [100 * fl["v2"]["false_positive_rate_mean"],
                                           100 * nl["v2"]["false_positive_rate_mean"]])],
              [ACCENT, ACCENT_MID], title="What the protocol flagged", fmt='0"%"', vmin=0,
              vmax=110, unit=20, label_fmt='0.0"%"')
    text(slide, LEFT, Inches(6.2), CONTENT_W, Inches(0.5),
         f"All {PG['global']['tamper_sent']} tampered messages were rejected.",
         size=20, bold=True, color=ACCENT, align=PP_ALIGN.CENTER)
    notes(slide, f"""
        Now the attack. 2 of the 10 clients flip their labels.
        Left chart: accuracy at the end of training. On FLNET2023, without protection the model
        gets {p(fl['none']['accuracy_mean'])}; with Krypsis {p(fl['v2']['accuracy_mean'])}.
        On NSL-KDD, without protection {p(nl['none']['accuracy_mean'])}; with Krypsis
        {p(nl['v2']['accuracy_mean'])}. On NSL-KDD this improvement is statistically significant.
        FLNET2023 has only 5 seeds, so it points the same way but is not significant.
        Right chart: the dark bars show how many poisoned updates were caught:
        {p(fl['v2']['detection_rate_mean'])} on FLNET2023 and {p(nl['v2']['detection_rate_mean'])}
        on NSL-KDD. The light bars, almost invisible, show honest updates wrongly flagged:
        only {p(fl['v2']['false_positive_rate_mean'])} and {p(nl['v2']['false_positive_rate_mean'])}.
        And every one of the {PG['global']['tamper_sent']} tampered messages was rejected by the
        integrity tag.
        These numbers are means over 5 seeds for FLNET2023 and 10 seeds for NSL-KDD.
    """)


def s17_comparison(prs):
    slide = base(prs, "Comparison: no protocol vs global vs Mondrian")
    n, g, m = PG["none"], PG["global"], PG["mondrian"]
    rows = [["", "No protocol", "Protocol + global", "Protocol + Mondrian"],
            ["Accuracy under attack", p(n["final_accuracy_mean"]), p(g["final_accuracy_mean"]),
             p(m["final_accuracy_mean"])],
            ["Attacks caught", "—", p(g["detection_rate_mean"]), p(m["detection_rate_mean"])],
            ["Honest wrongly flagged", "—", p(g["false_positive_rate_mean"]),
             p(m["false_positive_rate_mean"])],
            ["Tampered messages rejected", "not checked",
             f"{g['tamper_rejected']} / {g['tamper_sent']}",
             f"{m['tamper_rejected']} / {m['tamper_sent']}"]]
    best = 2
    widths = [Inches(3.9), Inches(2.6), Inches(2.75), Inches(2.68)]
    tbl = slide.shapes.add_table(len(rows), 4, *_e(LEFT, Inches(1.7), sum(widths),
                                                   Inches(0.8) * len(rows))).table
    for j, w in enumerate(widths):
        tbl.columns[j].width = w
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(0.8)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            if j == best:
                cell.fill.fore_color.rgb = ACCENT if i == 0 else ACCENT_LIGHT
            else:
                cell.fill.fore_color.rgb = WHITE if i else RGBColor(0xF3, 0xF5, 0xF6)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.text = val
            par = tf.paragraphs[0]
            par.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
            r = par.runs[0] if par.runs else par.add_run()
            r.font.size = Pt(20)
            r.font.name = FONT
            r.font.bold = i == 0 or j == best
            r.font.color.rgb = WHITE if (i == 0 and j == best) else (ACCENT if j == best else INK)
    tbl_el = tbl._tbl
    style = tbl_el.tblPr
    style.set("bandRow", "0")
    style.set("firstRow", "0")
    pt = PG["paired_t_test_global_vs_mondrian"]
    text(slide, LEFT, Inches(5.95), CONTENT_W, Inches(0.8),
         f"FLNET2023, 2 of 10 attackers, 15 seeds. Global vs Mondrian: no significant "
         f"difference (p = {pt['detection_rate']['p_value']:.2f} caught, "
         f"p = {pt['false_positive_rate']['p_value']:.2f} wrongly flagged).",
         size=17, color=GREY)
    notes(slide, f"""
        This table answers our research question. It is the FLNET2023 test with 15 seeds.
        Without the protocol, final accuracy under attack is {p(n['final_accuracy_mean'])}.
        With the protocol and a global threshold it is {p(g['final_accuracy_mean'])}, and with
        Mondrian {p(m['final_accuracy_mean'])}.
        Mondrian caught slightly more attacks, {p(m['detection_rate_mean'])} against
        {p(g['detection_rate_mean'])}, but it also wrongly flagged more honest clients,
        {p(m['false_positive_rate_mean'])} against {p(g['false_positive_rate_mean'])}.
        We used a paired t-test over the 15 seeds. Neither difference is significant: p equals
        {pt['detection_rate']['p_value']:.2f} and {pt['false_positive_rate']['p_value']:.2f}.
        So the global threshold, highlighted, is the best choice: highest accuracy, fewest false
        alarms, and simpler. Both versions rejected every tampered message.
    """)


def s18_conclusion(prs):
    slide = base(prs, "Conclusion: what we built and found")
    bullets(slide, LEFT, Inches(1.8), Inches(11.5), Inches(4.2), [
        ("Built:", "a federated attack detector over 10 real router clients."),
        ("Worked:", f"federated model nearly matches central ({p(FED_ROUTER['accuracy'], 2)} "
                    f"vs {p(CENTRAL['accuracy'])})."),
        ("Worked:", "protocol rejected all tampering and raised accuracy under attack."),
        ("Key finding:", "one global threshold is enough; Mondrian was not better."),
    ], size=24, gap=22)
    rect(slide, LEFT, Inches(5.6), CONTENT_W, Inches(0.95), fill=ACCENT_LIGHT, line=None,
         radius=0.1)
    text(slide, LEFT, Inches(5.6), CONTENT_W, Inches(0.95), "Thank you  ·  Questions?",
         size=24, bold=True, color=ACCENT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    notes(slide, """
        To conclude.
        We built Krypsis, a federated intrusion detector where 10 real routers train one model
        together without sharing their traffic.
        Federated training worked: it nearly matches the model trained on all the data.
        Our protocol worked: it rejected every tampered message, caught most poisoned updates,
        and kept accuracy higher under attack, for less than 1 percent extra message size.
        And our key finding: we expected a single global threshold to be unfair to honest clients
        with unusual data. It was not. Once scores are compared within each round, one global
        threshold is enough, and Mondrian gave no significant gain.
        Thank you. We are happy to take questions.
    """)


def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    for make in (s1_title, s2_intro, s3_objectives, s4_pipeline, s5_data, s6_clients,
                 s7_model, s8_protocol, s9_attack, s10_before_after, s11_code_dirichlet,
                 s12_code_fedavg, s13_code_protocol, s14_code_threshold, s15_accuracy,
                 s16_attack, s17_comparison, s18_conclusion):
        make(prs)
    prs.save(OUT_PATH)
    print(f"Saved {OUT_PATH} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    build()
