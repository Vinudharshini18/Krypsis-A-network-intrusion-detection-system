"""
Builds Krypsis_Final_Review.pptx — the final-review deck: a detailed
introduction, objectives and methodology, the results, comparisons with
existing approaches and between our own setups, conclusions and references.
Every slide has speaker notes.

Numbers are read from results/*.json (through build_deck.load_results), so
the deck always matches the latest experiment runs.

Run: ..\\venv\\Scripts\\python.exe build_final_review.py
Output: presentation/Krypsis_Final_Review.pptx
"""

import os
import re

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


def s_outline(prs):
    slide = base(prs, "Outline", "What this review covers")
    parts = [
        ("01", "Introduction", "The privacy problem, federated learning, the security gap"),
        ("02", "Objectives", "Five objectives and how far each was met"),
        ("03", "Methodology", "Data, model, the Krypsis protocol, experiment design"),
        ("04", "Results", "Detection, attacks, backdoors, robustness"),
        ("05", "Comparison", "Against existing approaches and between our setups"),
        ("06", "Conclusion", "Answers, limitations, future work, references"),
    ]
    for i, (num, name, desc) in enumerate(parts):
        col, row = divmod(i, 3)
        x = LEFT + col * Inches(6.0)
        y = Inches(2.15) + row * Inches(1.45)
        text(slide, x, y, Inches(1.0), Inches(0.7), num, size=30, font=SERIF, color=ACCENT)
        text(slide, x + Inches(1.0), y + Inches(0.05), Inches(4.8), Inches(1.1),
             [[(name, {"size": 17, "font": SERIF})], [(desc, {"size": 12, "color": INK_SOFT})]],
             spacing=1.25)
    notes(slide, "Six parts. Introduction, objectives and methodology are covered in detail; "
                 "then results, the comparisons, and our conclusions.")


# ---- 01 Introduction

def s_background(prs):
    slide = base(prs, "01 · Introduction", "Intrusion detection needs data nobody wants to share")
    text(slide, LEFT, Inches(2.0), Inches(5.6), Inches(0.35), "THE PROBLEM", size=11,
         bold=True, color=ACCENT)
    bullets(slide, LEFT, Inches(2.45), Inches(5.6), Inches(4.2), [
        ("Detectors learn from traffic.", "A network intrusion detection system (NIDS) "
         "classifies flows as normal or attack; it is only as good as the variety of "
         "traffic it has seen."),
        ("Pooling traffic is risky.", "Logs reveal hosts, services and internal "
         "structure — central collection creates a privacy and compliance problem."),
        ("One server, one point of failure.", "A central data lake is an attractive "
         "target and a bandwidth bottleneck."),
    ], size=13.5, gap=12)
    card(slide, Inches(7.0), Inches(2.0), Inches(5.5), Inches(3.45), fill=WHITE)
    text(slide, Inches(7.35), Inches(2.3), Inches(4.8), Inches(0.35), "WHERE IT MATTERS",
         size=11, bold=True, color=ACCENT)
    bullets(slide, Inches(7.35), Inches(2.75), Inches(4.85), Inches(3.6), [
        ("Hospitals, banks, universities", "training one shared detector without "
         "exposing their networks to each other."),
        ("ISPs and edge / IoT networks", "where every router or gateway already sees "
         "its own slice of traffic."),
        ("Cross-border security teams", "bound by different data-protection laws."),
    ], size=13, gap=12)
    notes(slide, "Start with the motivation: detection needs varied traffic, but traffic is "
                 "sensitive. Centralizing it is a privacy, legal and security problem. The "
                 "examples on the right are the settings where that matters most.")


def s_fl(prs):
    slide = base(prs, "01 · Introduction", "Federated learning: move the model, not the data")
    sw, sh = Inches(3.2), Inches(0.9)
    sx, sy = (W - sw) / 2, Inches(1.95)
    box_label(slide, sx, sy, sw, sh, "Aggregation server", "averages updates (FedAvg)",
              fill=ACCENT_SOFT, line=ACCENT, title_color=ACCENT)
    labels = ["Router 1", "Router 2", "Router 3", None, "Router 10"]
    bw, bh, by = Inches(1.9), Inches(0.9), Inches(4.35)
    step = Inches(2.35)
    x0 = (W - (4 * step + bw)) / 2
    centres = [x0 + i * step + bw / 2 for i in range(5)]
    bus = by - Inches(0.75)
    hrule(slide, centres[0], bus, centres[-1] - centres[0], color=MUTED, weight=1)
    line = _plain(slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                             *_e(W / 2, sy + sh, W / 2, bus)))
    line.line.color.rgb, line.line.width = MUTED, Pt(1)
    for cx, lab in zip(centres, labels):
        if lab is None:
            text(slide, cx - bw / 2, by + Inches(0.2), bw, Inches(0.5), "· · ·", size=20,
                 color=MUTED, align=PP_ALIGN.CENTER)
            continue
        box_label(slide, cx - bw / 2, by, bw, bh, lab, "local traffic + training")
        arrow(slide, cx - Inches(0.14), bus, cx - Inches(0.14), by, color=MUTED)
        arrow(slide, cx + Inches(0.14), by, cx + Inches(0.14), bus, color=ACCENT)
    text(slide, Inches(8.55), Inches(2.1), Inches(3.9), Inches(0.8),
         [[("↓  global model sent down", {"color": INK_SOFT, "size": 11.5})],
          [("↑  update sent up (weights only)", {"color": ACCENT, "size": 11.5})]],
         spacing=1.4)
    text(slide, LEFT, Inches(5.75), CONTENT_W, Inches(0.9),
         "Each round: the server sends the current model, every router trains it on its own "
         "traffic, and only the change in weights travels back. Raw traffic never leaves a "
         "router.", size=13.5, color=INK_SOFT, align=PP_ALIGN.CENTER)
    notes(slide, "Federated learning flips the flow. The server sends the model out; each "
                 "router trains it locally and sends back only weight updates. In our project "
                 "the clients are 10 real routers from the FLNET2023 dataset.")


def s_gap(prs):
    slide = base(prs, "01 · Introduction", "But the updates themselves become the attack surface")
    cols = [
        ("Tampering in transit", "An update can be corrupted or modified between router "
         "and server. Generic transports (HTTP + JSON) carry no per-client integrity check."),
        ("Poisoned updates", "A compromised router can train on wrong labels (label "
         "flipping) or plant a hidden rule (backdoor) and send a valid-looking update."),
        ("Honest but different", "Routers genuinely see different traffic (non-IID). "
         "Outlier-based defenses can mistake an honest, unusual router for an attacker."),
    ]
    for i, (title, body) in enumerate(cols):
        x = LEFT + i * Inches(3.97)
        card(slide, x, Inches(2.05), Inches(3.75), Inches(2.55))
        text(slide, x + Inches(0.3), Inches(2.3), Inches(3.2), Inches(0.4), f"0{i + 1}",
             size=20, font=SERIF, color=ACCENT)
        text(slide, x + Inches(0.3), Inches(2.8), Inches(3.2), Inches(1.75),
             [[(title, {"bold": True, "size": 14})], [(body, {"size": 12, "color": INK_SOFT})]],
             spacing=1.25)
    text(slide, LEFT, Inches(4.95), CONTENT_W, Inches(0.35), "HOW IT IS USUALLY HANDLED",
         size=11, bold=True, color=ACCENT)
    bullets(slide, LEFT, Inches(5.35), CONTENT_W, Inches(1.5), [
        ("Efficiency work", "(compression, client selection) shrinks updates but ignores security."),
        ("Robust aggregation", "(Krum, trimmed mean) runs on the server after every update is "
         "fully received — on every client, every round."),
    ], size=13, gap=6)
    notes(slide, "Federated learning removes the data-sharing problem but creates a new one: "
                 "the updates. Three threats: tampering, poisoning, and the subtle one — honest "
                 "routers that look unusual. Existing work treats efficiency and security "
                 "separately, and robust aggregation is applied after everything is received.")


def s_question(prs):
    slide = base(prs, "01 · Introduction", "Research gap and question")
    card(slide, LEFT, Inches(2.0), Inches(5.7), Inches(4.5), fill=WHITE)
    text(slide, LEFT + Inches(0.35), Inches(2.25), Inches(5.0), Inches(0.35), "THE GAP",
         size=11, bold=True, color=ACCENT)
    text(slide, LEFT + Inches(0.35), Inches(2.7), Inches(5.0), Inches(3.7),
         "Security and communication are designed separately. We fuse them into the update "
         "protocol itself: every update carries an integrity tag and a compact statistical "
         "fingerprint, so tampered or suspicious updates can be rejected cheaply — before the "
         "expensive aggregation step.\n\nOutlier checks of this kind compare each update with "
         "the consensus, which raises a fairness question for non-IID routers.",
         size=13.5, color=INK, spacing=1.3)
    rect(slide, Inches(6.9), Inches(2.0), Inches(5.63), Inches(4.5), fill=ACCENT_SOFT,
         line=None, radius=0.04)
    text(slide, Inches(7.25), Inches(2.25), Inches(5.0), Inches(0.35), "RESEARCH QUESTION",
         size=11, bold=True, color=ACCENT)
    text(slide, Inches(7.25), Inches(2.75), Inches(5.0), Inches(2.5),
         "Does one global anomaly threshold wrongly flag honest, non-IID routers — and do "
         "per-cluster (Mondrian) thresholds reduce those false alarms without missing real "
         "attacks?", size=17, font=SERIF, color=INK, spacing=1.3)
    text(slide, Inches(7.25), Inches(5.35), Inches(5.0), Inches(1.0),
         "Mondrian calibration: one threshold per group of similar clients instead of one "
         "for everyone — borrowed from conformal prediction.", size=11.5, color=INK_SOFT)
    notes(slide, "Our gap: fuse integrity checking and cheap anomaly filtering into the "
                 "protocol. Our research question tests whether a global threshold is unfair "
                 "to unusual honest routers, and whether per-group thresholds fix it.")


# ---- 02 Objectives

def s_objectives(prs):
    slide = base(prs, "02 · Objectives", "Five objectives")
    objs = [
        ("Federated detector", "Train one intrusion detector across distributed clients "
         "without centralizing raw traffic.",
         f"Met — FedAvg over 10 routers: {pct(R['fed_router']['accuracy'], 2)}"),
        ("Security-fused protocol", "Design an update protocol with an integrity tag and a "
         "fingerprint that filters bad updates before aggregation.",
         "Met — HMAC + verifiable fingerprint + 3 anomaly scores"),
        ("Detection quality", "Evaluate accuracy, precision, recall and F1 under federated "
         "training.", "Met — binary and 11-class, two datasets"),
        ("Communication & cost", "Measure the protocol's overhead and server cost against a "
         "generic HTTP/JSON transfer.",
         f"Met — +{pct(OVERHEAD, 2)} overhead; JSON is {JSON_X:.1f}× larger"),
        ("Robustness & the research question", "Test non-IID clients, poisoning, dropout and "
         "global vs Mondrian thresholds, with repeated seeds and significance tests.",
         "Met — 235 federated runs; Mondrian not better"),
    ]
    y = Inches(1.95)
    for i, (name, desc, status) in enumerate(objs):
        ry = y + i * Inches(0.95)
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
    notes(slide, "Five objectives, each with how far it was met. The right column is the "
                 "evidence; every number comes from our results files.")


def s_scope(prs):
    slide = base(prs, "02 · Objectives", "Scope and assumptions")
    text(slide, LEFT, Inches(2.0), Inches(5.6), Inches(0.35), "IN SCOPE", size=11, bold=True,
         color=ACCENT)
    bullets(slide, LEFT, Inches(2.45), Inches(5.6), Inches(4.2), [
        "Simulated federation on recorded router traffic (FLNET2023), repeated on NSL-KDD",
        "Binary (normal vs attack) and 11-class detection",
        "Integrity tag, fingerprint, anomaly filter, second check, weight cap",
        "Attacks: tampering, label flipping, backdoor; client dropout; traffic shift",
        "Repeated seeds with paired t-tests",
    ], size=14, gap=12)
    text(slide, Inches(7.0), Inches(2.0), Inches(5.5), Inches(0.35), "ASSUMPTIONS & LIMITS",
         size=11, bold=True, color=BRONZE)
    bullets(slide, Inches(7.0), Inches(2.45), Inches(5.5), Inches(4.2), [
        "Clients and server run in one process — no real network deployment",
        "Each client shares a pre-distributed secret key with the server",
        "The first 5 rounds are clean and used to calibrate thresholds",
        "FLNET2023 is emulated (CORE): its binary task is unusually easy",
        "Attackers control at most 20% of clients and do not adapt to the filter",
    ], size=14, gap=12)
    notes(slide, "Be explicit about what was and was not done. In particular: everything is "
                 "simulated in one process, keys are pre-shared, and the attackers are not "
                 "adaptive. These are the honest limits of the evaluation.")


# ---- 03 Methodology

def s_architecture(prs):
    slide = base(prs, "03 · Methodology", "System architecture")
    y, h = Inches(2.55), Inches(1.35)
    blocks = [
        (LEFT, Inches(2.15), "Router client", "local flows → local training → update Δw"),
        (Inches(3.35), Inches(2.25), "Krypsis message", "header · fingerprint · payload · HMAC"),
        (Inches(6.05), Inches(3.2), "Server checks", "verify tag → verify fingerprint → "
         "score → threshold → second check"),
        (Inches(9.7), Inches(2.0), "Capped FedAvg", "weighted average, ≤ 15% per client"),
    ]
    for i, (x, w, title, body) in enumerate(blocks):
        accent = i in (1, 2)
        box_label(slide, x, y, w, h, title, body, fill=ACCENT_SOFT if accent else WHITE,
                  line=ACCENT if accent else LINE, title_color=ACCENT if accent else INK)
        if i < len(blocks) - 1:
            nx = blocks[i + 1][0]
            arrow(slide, x + w + Inches(0.03), y + h / 2, nx - Inches(0.03), y + h / 2,
                  color=ACCENT)
    ax1, ax2 = Inches(6.75), Inches(8.55)
    for x in (ax1, ax2):
        arrow(slide, x, y, x, y - Inches(0.42), color=BRONZE)
    text(slide, ax1 - Inches(2.9), y - Inches(0.62), Inches(2.8), Inches(0.3),
         "rejected: tag or fingerprint mismatch", size=10, color=BRONZE, align=PP_ALIGN.RIGHT)
    text(slide, ax2 + Inches(0.1), y - Inches(0.62), Inches(2.8), Inches(0.3),
         "flagged → second check", size=10, color=BRONZE)
    loop_y = y + h + Inches(0.45)
    rx, fx = LEFT + Inches(1.07), Inches(10.7)
    hrule(slide, rx, loop_y, fx - rx, color=MUTED, weight=1)
    arrow(slide, fx, y + h, fx, loop_y, color=MUTED)
    arrow(slide, rx, loop_y, rx, y + h, color=MUTED)
    text(slide, Inches(4.4), loop_y + Inches(0.08), Inches(4.6), Inches(0.3),
         "new global model sent to every router — next round", size=10.5, color=INK_SOFT,
         align=PP_ALIGN.CENTER)
    cols = [
        ("ON THE ROUTER", "Trains on its own flows and wraps the weight change in a Krypsis "
                          "message. Raw traffic never leaves."),
        ("ON THE WIRE", "Header, fingerprint, update and HMAC tag — 0.67% larger than the "
                        "bare update."),
        ("ON THE SERVER", "Checks, scores and filters every update before averaging — it sees "
                          "updates and fingerprints, never traffic."),
    ]
    hrule(slide, LEFT, Inches(5.25), CONTENT_W)
    for i, (title, body) in enumerate(cols):
        x = LEFT + i * Inches(3.97)
        text(slide, x, Inches(5.45), Inches(3.7), Inches(1.3),
             [[(title, {"bold": True, "size": 10.5, "color": ACCENT})],
              [(body, {"size": 12, "color": INK_SOFT})]], spacing=1.25)
    notes(slide, "One round, left to right: the router trains locally and wraps its update in "
                 "a Krypsis message; the server verifies it, scores it, filters it, and "
                 "averages the accepted updates with a per-client cap. The new model goes back "
                 "to every router.")


def s_dataset(prs):
    slide = base(prs, "03 · Methodology", "Data: FLNET2023 — ten routers, ten clients")
    text(slide, LEFT, Inches(1.85), Inches(4.4), Inches(4.8), [
        [("FLNET2023", {"bold": True, "size": 14})],
        [("Kumar et al., MILCOM 2023. Flows recorded at 10 routers of a 40-node network "
          "emulated with CORE; 83 CICFlowMeter features per flow.", {"size": 12,
                                                                     "color": INK_SOFT})],
        [("", {})],
        [("11 traffic types", {"bold": True, "size": 14})],
        [("Normal; DDoS bot / dyn / stomp / tcp; DoS hulk / slowhttp; Web SQLi / XSS / "
          "command injection; Infiltration MITM.", {"size": 12, "color": INK_SOFT})],
        [("", {})],
        [("Why this dataset", {"bold": True, "size": 14})],
        [("Each router is a natural client with its own uneven attack mix — real non-IID "
          "data, not a simulated split.", {"size": 12, "color": INK_SOFT})],
        [("", {})],
        [("Second dataset: NSL-KDD", {"bold": True, "size": 14})],
        [("Classic benchmark; 10 clients by Dirichlet split. Used to replicate the protocol "
          "results on a harder task.", {"size": 12, "color": INK_SOFT})],
    ], spacing=1.2)
    rows = [["Router", "Flows", "Attack %", "Attack types seen"]]
    rows += [[str(r), f"{n:,}", f"{a:.1f}%", t] for r, n, a, t in ROUTERS]
    table(slide, Inches(5.55), Inches(1.95), [Inches(0.8), Inches(1.05), Inches(1.05),
                                              Inches(4.1)], rows, size=11, row_h=Inches(0.42))
    text(slide, Inches(5.55), Inches(6.65), Inches(7), Inches(0.3),
         "Training flows after 10% sampling; all ten routers also carry normal traffic.",
         size=10, color=MUTED)
    notes(slide, "FLNET2023 was built for federated intrusion detection: 10 routers, each "
                 "seeing a different mix. Router 3 is mostly normal; router 4 is 92% attack; "
                 "router 10 is a quarter of all data. NSL-KDD is our second dataset.")


def s_preprocess(prs):
    slide = base(prs, "03 · Methodology", "Preprocessing")
    steps = [
        ("Load & tag", "Each CSV is tagged with its router number, read from the file name. "
                       "The separate TEST capture is the test set."),
        ("Sample", "Each file sampled to 10% (minimum 2,000 rows) — 4.8 M flows is too many "
                   "for repeated federated runs; router proportions are kept."),
        ("Remove identifiers", "src_ip, dst_ip, src_port, timestamp dropped so the model "
                               "learns behaviour, not who the attacker is."),
        ("Clean", "Rows with inf / NaN values dropped (none remained after sampling); "
                  "12 constant columns removed."),
        ("Scale", "Signed log(1+x), then min-max to [0, 1], fitted on training data only."),
    ]
    for i, (name, body) in enumerate(steps):
        y = Inches(1.95) + i * Inches(0.82)
        rect(slide, LEFT, y + Inches(0.06), Inches(0.42), Inches(0.42), fill=ACCENT_SOFT,
             line=None, radius=0.5)
        text(slide, LEFT, y + Inches(0.06), Inches(0.42), Inches(0.42), str(i + 1), size=12,
             bold=True, color=ACCENT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, LEFT + Inches(0.65), y, Inches(6.6), Inches(0.8),
             [[(name, {"bold": True, "size": 13.5})], [(body, {"size": 11.5, "color": INK_SOFT})]],
             spacing=1.15)
    card(slide, Inches(8.4), Inches(1.95), Inches(4.13), Inches(4.2), fill=WHITE)
    text(slide, Inches(8.7), Inches(2.2), Inches(3.6), Inches(0.35), "RESULT", size=11,
         bold=True, color=ACCENT)
    for i, (num, lab) in enumerate([("66", "features per flow"), ("564,007", "training flows"),
                                    ("79,491", "test flows"), ("10", "router clients")]):
        y = Inches(2.65) + i * Inches(0.85)
        text(slide, Inches(8.7), y, Inches(3.6), Inches(0.8),
             [[(num, {"size": 22, "font": SERIF, "color": INK})],
              [(lab, {"size": 11, "color": INK_SOFT})]], spacing=1.0)
    notes(slide, "Five steps. The important design choice is removing IP addresses, the "
                 "source port and timestamps — otherwise the model could memorise which "
                 "machine is the attacker instead of learning what attacks look like.")


def s_model(prs):
    slide = base(prs, "03 · Methodology", "Model and training")
    layers = [("Input", "66"), ("Dense", "256"), ("Dense", "128"), ("Dense", "64"),
              ("Output", "1 · sigmoid")]
    bw, gap = Inches(1.7), Inches(0.62)
    x0, y0 = LEFT + Inches(0.1), Inches(2.15)
    for i, (kind, size_) in enumerate(layers):
        x = x0 + i * (bw + gap)
        box_label(slide, x, y0, bw, Inches(0.95), size_, kind,
                  fill=ACCENT_SOFT if 0 < i < 4 else WHITE,
                  line=ACCENT if 0 < i < 4 else LINE, title_color=INK, size=14)
        if i < len(layers) - 1:
            arrow(slide, x + bw + Inches(0.04), y0 + Inches(0.475), x + bw + gap - Inches(0.04),
                  y0 + Inches(0.475), color=MUTED)
    text(slide, x0, y0 + Inches(1.05), Inches(11.5), Inches(0.35),
         "ReLU, dropout 0.3 / 0.3 / 0.2, L2 weight decay · 58,369 parameters · 11-class "
         "variant uses a softmax output", size=11.5, color=INK_SOFT, align=PP_ALIGN.CENTER)
    cols = [
        ("Centralized baseline", [
            "All training data in one place",
            "Stratified 90 / 10 validation split",
            "Class weights, early stopping",
            "Decision threshold tuned on validation",
        ]),
        ("Federated (FedAvg)", [
            "10 router clients, one model each round",
            "Phase 6: 15 rounds × 2 local epochs",
            "Attack runs: 12 rounds × 1 epoch",
            "Average weighted by client data size",
        ]),
        ("Reproducibility", [
            "Fixed seeds for NumPy, Python, TensorFlow",
            "Single-threaded ops (deterministic)",
            "Same seed = same attackers and init",
            "Every number from results/*.json",
        ]),
    ]
    for i, (title, items) in enumerate(cols):
        x = LEFT + i * Inches(3.97)
        card(slide, x, Inches(3.95), Inches(3.75), Inches(2.75))
        text(slide, x + Inches(0.3), Inches(4.15), Inches(3.2), Inches(0.35), title,
             size=13.5, bold=True)
        bullets(slide, x + Inches(0.3), Inches(4.6), Inches(3.25), Inches(2.0), items,
                size=11.5, gap=4)
    notes(slide, "A standard multilayer perceptron — the right tool for tabular flow "
                 "features, and it averages cleanly under FedAvg. Centralized training is our "
                 "upper bound; federated training is the real system.")


def s_message(prs):
    slide = base(prs, "03 · Methodology", "The Krypsis update message")
    parts = [("Length", "4 B", Inches(1.25), BG_DEEP),
             ("Header + fingerprint", "client · round · sample count · L2 norm · 4 layer "
              "norms · 64-number sketch", Inches(4.0), ACCENT_SOFT),
             ("Payload", f"model update Δw · {COMM['raw_payload_bytes']:,} B (float32)",
              Inches(4.45), WHITE),
             ("Tag", "HMAC-SHA256 · 32 B", Inches(2.03), BRONZE_SOFT)]
    x = LEFT
    for name, body, w, fill in parts:
        rect(slide, x, Inches(2.05), w, Inches(1.15), fill=fill, line=LINE)
        text(slide, x + Inches(0.15), Inches(2.15), w - Inches(0.3), Inches(1.0),
             [[(name.upper(), {"bold": True, "size": 10.5, "color": ACCENT})],
              [(body, {"size": 11.5, "color": INK})]], spacing=1.2)
        x += w
    cols = [
        ("Integrity tag", "HMAC over header and payload with a key shared only by that "
                          "router and the server. One changed byte → rejected."),
        ("Fingerprint", "A compact summary: the update's size overall and per layer, plus a "
                        "random projection (sketch) that preserves its direction."),
        ("Verifiable", "The server recomputes the fingerprint from the payload — a client "
                       "cannot send an innocent-looking fake."),
    ]
    for i, (title, body) in enumerate(cols):
        x = LEFT + i * Inches(3.97)
        text(slide, x, Inches(3.6), Inches(3.7), Inches(1.6),
             [[(title, {"bold": True, "size": 14})], [(body, {"size": 12, "color": INK_SOFT})]],
             spacing=1.25)
    hrule(slide, LEFT, Inches(5.35), CONTENT_W)
    stats = [(f"+{COMM['krypsis_overhead_bytes']:,} B", f"overhead per update ({pct(OVERHEAD, 2)})"),
             (f"{COMM['http_json_bytes'] / 1000:,.0f} KB", f"same update as HTTP/JSON ({JSON_X:.1f}×)"),
             ("~2 ms", "verification per message")]
    for i, (num, lab) in enumerate(stats):
        x = LEFT + i * Inches(3.97)
        text(slide, x, Inches(5.55), Inches(3.7), Inches(1.0),
             [[(num, {"size": 22, "font": SERIF})], [(lab, {"size": 11, "color": INK_SOFT})]],
             spacing=1.05)
    notes(slide, "Every update is wrapped like this. The tag catches tampering; the "
                 "fingerprint lets the server judge the update cheaply; and because the server "
                 "recomputes it, a cheating client cannot fake it. All of this costs well under "
                 "one percent of the message size.")


def s_server(prs):
    slide = base(prs, "03 · Methodology", "Server decision pipeline")
    steps = [
        ("Verify tag", "HMAC mismatch → reject", BRONZE),
        ("Verify fingerprint", "Recomputed ≠ claimed → reject", BRONZE),
        ("Score", "Size, direction vs. consensus, change vs. own last update", ACCENT),
        ("Standardize", "Robust z-score within the round (median / MAD)", ACCENT),
        ("Threshold", "Conformal quantile from 5 clean rounds — global or Mondrian", ACCENT),
        ("Second check", "Flagged update rescued if close to a trimmed-mean reference", ACCENT),
        ("Aggregate", "FedAvg on accepted updates, ≤ 15% weight per client", INK),
    ]
    for i, (name, body, color) in enumerate(steps):
        y = Inches(1.95) + i * Inches(0.66)
        rect(slide, LEFT, y, Inches(0.08), Inches(0.5), fill=color, line=None)
        text(slide, LEFT + Inches(0.3), y, Inches(2.4), Inches(0.5), name, size=13.5,
             bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, LEFT + Inches(2.7), y, Inches(4.5), Inches(0.5), body, size=12,
             color=INK_SOFT, anchor=MSO_ANCHOR.MIDDLE)
    card(slide, Inches(8.3), Inches(1.95), Inches(4.23), Inches(4.55), fill=WHITE)
    text(slide, Inches(8.6), Inches(2.2), Inches(3.7), Inches(4.2), [
        [("WHY STANDARDIZE PER ROUND", {"bold": True, "size": 11, "color": ACCENT})],
        [("Our first design used fixed thresholds. Once training converged every honest "
          "update became small and noisy, and 65–96% of honest updates were flagged.",
          {"size": 12})],
        [("", {})],
        [("Scoring each update relative to the other clients in the same round fixed it — "
          "kept as a documented negative result.", {"size": 12, "color": INK_SOFT})],
        [("", {})],
        [("GLOBAL vs MONDRIAN", {"bold": True, "size": 11, "color": ACCENT})],
        [("Global: one threshold for all clients. Mondrian: clients clustered by their "
          "calibration sketches (k-means, k = 3), one threshold per cluster.", {"size": 12})],
    ], spacing=1.2)
    notes(slide, "Seven steps. The first two are hard checks — reject. Then three cheap "
                 "scores, standardized within the round, compared to calibrated thresholds. "
                 "Flagged updates get a second, more careful check instead of being thrown "
                 "away. The global-versus-Mondrian choice is our research question.")


def s_design(prs):
    slide = base(prs, "03 · Methodology", "Threat model and experiment design")
    text(slide, LEFT, Inches(1.95), Inches(5.6), Inches(0.35), "ATTACKS", size=11, bold=True,
         color=ACCENT)
    bullets(slide, LEFT, Inches(2.4), Inches(5.6), Inches(2.6), [
        ("Tampering —", "one byte of an honest message flipped in transit."),
        ("Label flipping —", "2 of 10 clients train on inverted labels."),
        ("Backdoor —", "2 clients add one attack type labelled normal."),
        ("Stress —", "client dropout (0–40%), traffic shift, 10–40 clients."),
    ], size=12.5, gap=7)
    text(slide, LEFT, Inches(4.75), Inches(5.6), Inches(0.35), "METRICS", size=11, bold=True,
         color=ACCENT)
    bullets(slide, LEFT, Inches(5.2), Inches(5.6), Inches(1.6), [
        "Accuracy, precision, recall, F1, macro-F1",
        "Poisoned updates caught · honest updates wrongly excluded",
        "Backdoor success rate · bytes per message · server ms per round",
    ], size=12.5, gap=5)
    rows = [["Experiment", "Compared", "Runs"],
            ["Protocol (Ph. 8)", "none · global · Mondrian", "45"],
            ["Defenses (Ph. 9)", "none · v1 · v2 · v2-Mondrian", "120"],
            ["Robustness (Ph. 11)", "dropout · shift · scale", "70"],
            ["Multi-class (Ph. 10)", "central · IID · routers", "3"]]
    table(slide, Inches(6.95), Inches(2.0), [Inches(2.15), Inches(2.75), Inches(0.68)], rows,
          size=12, row_h=Inches(0.5))
    text(slide, Inches(6.95), Inches(4.75), Inches(5.6), Inches(1.8), [
        [("STATISTICS", {"bold": True, "size": 11, "color": ACCENT})],
        [("Every setting repeated over random seeds (5–15). Policies compared on the same "
          "seeds — same attackers, same initial model — with paired t-tests; p < 0.05 counts "
          "as significant.", {"size": 12.5, "color": INK})],
    ], spacing=1.25)
    notes(slide, "We attack our own system four ways and measure detection, false alarms, "
                 "accuracy and cost. Every comparison is paired by seed so differences are "
                 "not just luck, and we report p-values.")


# ---- 04 Results

def s_baseline(prs):
    slide = base(prs, "04 · Results", "Baseline detection — and why we did not stop there")
    stats = [(pct(R["central"]["accuracy"]), "centralized"),
             (pct(R["fed_router"]["accuracy"], 2), "FedAvg · 10 real routers"),
             (pct(R["fed_iid"]["accuracy"], 3), "FedAvg · IID split")]
    for i, (num, lab) in enumerate(stats):
        x = LEFT + i * Inches(3.0)
        text(slide, x, Inches(2.0), Inches(2.9), Inches(1.1),
             [[(num, {"size": 30, "font": SERIF})], [(lab, {"size": 11.5, "color": INK_SOFT})]],
             spacing=1.05)
    text(slide, LEFT, Inches(3.35), Inches(8.8), Inches(0.6),
         "Binary normal-vs-attack accuracy on FLNET2023's separate TEST capture (79,491 flows).",
         size=12.5, color=INK_SOFT)
    rect(slide, LEFT, Inches(4.15), CONTENT_W, Inches(2.45), fill=BRONZE_SOFT, line=None,
         radius=0.04)
    text(slide, LEFT + Inches(0.35), Inches(4.35), Inches(11), Inches(2.2), [
        [("WE CHECKED THE 100% INSTEAD OF TRUSTING IT", {"bold": True, "size": 11,
                                                         "color": BRONZE})],
        [("Identifiers were already removed. Yet a single threshold on one feature (forward "
          "packet count) scores 97.5%, a depth-2 decision tree 99.2%, and a depth-3 tree "
          "99.99%.", {"size": 13.5})],
        [("The emulated traffic is simply very easy to separate. So binary accuracy cannot "
          "show differences between setups — we added 11-class detection, and judged the "
          "protocol by how attacks change accuracy.", {"size": 13.5, "color": INK_SOFT})],
    ], spacing=1.3)
    notes(slide, "Federated training matches centralized training almost exactly. But a "
                 "perfect score needs checking: the dataset turned out to be separable by a "
                 "single feature. That is why the rest of the results focus on multi-class "
                 "detection and on attacks.")


def s_multiclass(prs):
    slide = base(prs, "04 · Results", "Multi-class detection reveals the non-IID problem")
    picture(slide, "multiclass_recall.png", LEFT, Inches(1.85), h=Inches(4.95))
    x = Inches(8.35)
    text(slide, x, Inches(1.95), Inches(4.2), Inches(0.35), "MACRO-F1", size=11, bold=True,
         color=ACCENT)
    for i, (key, lab) in enumerate((("centralized", "Centralized"),
                                    ("federated_iid", "FedAvg · IID"),
                                    ("federated_router", "FedAvg · real routers"))):
        y = Inches(2.4) + i * Inches(0.78)
        text(slide, x, y, Inches(4.2), Inches(0.75),
             [[(f"{MC[key]['macro_f1']:.2f}", {"size": 22, "font": SERIF,
                                               "color": BRONZE if i == 2 else INK})],
              [(lab, {"size": 11, "color": INK_SOFT})]], spacing=1.0)
    text(slide, x, Inches(4.85), Inches(4.2), Inches(1.9),
         "Every attack type held by only one or two routers is never learned over the real "
         "routers — the other clients' updates average it away. DDoS-tcp survives (70%) "
         "because its router carries 25% of the weight.", size=12, color=INK, spacing=1.25)
    notes(slide, "When the model must name the attack, federated training over real routers "
                 "loses half its macro-F1. Attack types seen at only one router are averaged "
                 "away. This is the non-IID problem our project is about, made visible.")


def s_attack(prs):
    slide = base(prs, "04 · Results", "The protocol under label-flipping attack")
    picture(slide, "attack_accuracy_by_round.png", LEFT, Inches(1.8), w=Inches(8.3))
    x = Inches(9.4)
    rows = [("FLNET2023", FL["none"]["accuracy_mean"], FL["v1"]["accuracy_mean"], "v1"),
            ("NSL-KDD", NL["none"]["accuracy_mean"], NL["v2"]["accuracy_mean"], "v2")]
    text(slide, x, Inches(1.95), Inches(3.2), Inches(0.35), "ACCURACY UNDER ATTACK", size=11,
         bold=True, color=ACCENT)
    for i, (name, none_, prot, ver) in enumerate(rows):
        y = Inches(2.4) + i * Inches(1.2)
        text(slide, x, y, Inches(3.2), Inches(1.1),
             [[(name, {"bold": True, "size": 12.5})],
              [(f"{pct(none_)}  →  {pct(prot)}", {"size": 20, "font": SERIF})],
              [(f"no defense → protocol {ver}", {"size": 10.5, "color": INK_SOFT})]],
             spacing=1.1)
    text(slide, x, Inches(4.95), Inches(3.2), Inches(1.8),
         "NSL-KDD: significant (p = 0.009, 10 seeds). FLNET2023: same direction, not "
         "significant with 5 seeds. 105 / 105 tampered messages rejected.",
         size=11.5, color=INK_SOFT, spacing=1.25)
    notes(slide, "Attackers start after the dashed line. Without protection accuracy swings "
                 "and drops; with the protocol it stays near the clean level. The NSL-KDD "
                 "result is statistically significant; FLNET2023 points the same way.")


def s_backdoor(prs):
    slide = base(prs, "04 · Results", "Backdoors and communication cost")
    picture(slide, "backdoor_success.png", LEFT, Inches(1.85), h=Inches(3.6))
    picture(slide, "message_size.png", Inches(6.85), Inches(1.95), w=Inches(5.6))
    text(slide, LEFT, Inches(5.6), Inches(5.6), Inches(1.2),
         f"NSL-KDD backdoor success {pct(NB['none']['backdoor_asr_mean'])} → "
         f"{pct(NB['v2']['backdoor_asr_mean'])} (p < 0.001). On FLNET2023 the backdoor failed "
         "even without a defense — honest routers outvote it.", size=12, color=INK_SOFT,
         spacing=1.25)
    text(slide, Inches(6.85), Inches(5.6), Inches(5.6), Inches(1.2),
         f"The header, fingerprint and tag add {pct(OVERHEAD, 2)}; plain HTTP/JSON would be "
         f"{JSON_X:.1f}× the size of the raw update.", size=12, color=INK_SOFT, spacing=1.25)
    notes(slide, "Left: the protocol cuts the backdoor's success by about three quarters on "
                 "NSL-KDD. Right: all of the protection costs less than one percent in message "
                 "size, while JSON would be more than five times larger.")


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
        row["fpr"] = RB["dropout"][str(p)]["v2"]["false_positive_rate_mean"]
        out[p] = row
    return out


def s_dropout(prs):
    slide = base(prs, "04 · Results", "Robustness I — routers dropping out")
    picture(slide, "dropout_accuracy.png", LEFT, Inches(1.8), w=Inches(8.4))
    stats = _dropout_stats()
    rows = [["Offline", "No defense", "Protocol", "Caught"]]
    rows += [[f"{100 * p:.0f}%", pct(v["none"]), pct(v["v2"]), pct(v["caught"], 0)]
             for p, v in stats.items()]
    table(slide, Inches(9.35), Inches(1.95), [Inches(0.72), Inches(0.98), Inches(0.85),
                                              Inches(0.63)], rows, size=11,
          row_h=Inches(0.48))
    text(slide, Inches(9.35), Inches(4.05), Inches(3.18), Inches(2.6),
         "Accuracy is the mean over all attack rounds. The protocol helps at every level and "
         "keeps wrongly excluded honest updates under 1%, but its advantage shrinks as more "
         "routers drop out — with ~6 online, 2 attackers pull the round's median.",
         size=11.5, color=INK_SOFT, spacing=1.25)
    notes(slide, "Each round every router is offline with some probability. The protocol "
                 "still helps, but at 40% dropout it catches only about a third of the "
                 "poisoned updates — the consensus it compares against is built from fewer "
                 "routers.")


def s_scale(prs):
    slide = base(prs, "04 · Results", "Robustness II — more clients, and a traffic shift")
    picture(slide, "scale_global_vs_mondrian.png", LEFT, Inches(1.8), w=Inches(8.4))
    sc = RB["scale"]
    rows = [["Clients", "Caught", "Honest excl.", "Server"]]
    for k in ("1", "2", "4"):
        e = sc[k]["v2"]
        rows.append([str(10 * int(k)), pct(e["detection_rate_mean"], 0),
                     pct(e["false_positive_rate_mean"]),
                     f"{e['mean_server_ms_per_round_mean']:.0f} ms"])
    table(slide, Inches(9.35), Inches(1.95), [Inches(0.72), Inches(0.7), Inches(1.06),
                                              Inches(0.7)], rows, size=11,
          row_h=Inches(0.48))
    shift = next(iter(RB["shift"].values()))["v2"]
    text(slide, Inches(9.35), Inches(4.05), Inches(3.18), Inches(2.6), [
        [("Global threshold shown. More clients give a steadier median and smaller "
          "attackers; server time grows about linearly.", {"size": 11.5, "color": INK_SOFT})],
        [("", {"size": 6})],
        [("Traffic shift: ", {"bold": True, "size": 11.5}),
         (f"router 3 suddenly seeing DDoS traffic was wrongly excluded "
          f"{pct(shift['shifted_client_excluded_rate_mean'], 0)} of the time.",
          {"size": 11.5, "color": INK_SOFT})],
    ], spacing=1.25)
    notes(slide, "Splitting each router into sub-clients gives 20 and 40 clients. More "
                 "clients make the filter stronger and the server cost stays in "
                 "milliseconds. Mondrian is still not better. An honest router whose traffic "
                 "changed was never wrongly rejected.")


def s_compare_existing(prs):
    slide = base(prs, "05 · Comparison", "Compared with existing approaches")
    rows = [
        ["Approach", "Tamper check", "Filters poisoned updates", "When / cost", "Evidence here"],
        ["Plain FedAvg\n(McMahan 2017)", "No", "No", "—",
         f"Label flip: {pct(FL['none']['accuracy_mean'])} FLNET, {pct(NL['none']['accuracy_mean'])} NSL"],
        ["HTTP + JSON transfer", "Channel only (TLS)", "No",
         f"{JSON_X:.1f}× message size", "Measured: 1,316 KB / update"],
        ["Krum\n(Blanchard 2017)", "No", "Yes, every round",
         "After full receipt · pairwise O(n²·d)", "Not implemented (literature)"],
        ["Trimmed mean\n(Yin 2018)", "No", "Yes, every round",
         "After full receipt · O(n·d·log n)", "Used inside our second check"],
        ["Krypsis (ours)", "Per-client HMAC", "Yes — cheap filter first",
         f"Before aggregation · +{pct(OVERHEAD, 2)} · ~2 ms / msg",
         f"Label flip: {pct(FL['v1']['accuracy_mean'])} FLNET, {pct(NL['v2']['accuracy_mean'])} NSL"],
    ]
    table(slide, LEFT, Inches(1.95), [Inches(2.35), Inches(1.75), Inches(2.3), Inches(2.85),
                                      Inches(2.48)], rows, size=11.5, row_h=Inches(0.72),
          bold_cols=(0,), shade_rows=(5,))
    text(slide, LEFT, Inches(6.4), CONTENT_W, Inches(0.5),
         "Rows without measurements are characterised from the cited papers; Krypsis adds a "
         "per-client integrity tag and moves filtering before aggregation, and keeps robust "
         "aggregation as a second step only for flagged rounds.", size=10.5, color=MUTED)
    notes(slide, "Plain FedAvg has no protection. HTTP plus TLS protects the channel but not "
                 "against a malicious client. Krum and trimmed mean filter updates, but only "
                 "after receiving everything, every round. Krypsis adds per-client integrity "
                 "and a cheap filter first. Rows marked as literature were not re-implemented.")


def s_compare_ours(prs):
    slide = base(prs, "05 · Comparison", "Comparison between our own setups")
    rows = [["Dataset · attack", "Metric", "No defense", "Protocol v1", "Protocol v2", "v2 Mondrian"]]

    def fmt(e, k):
        return pct(e[f"{k}_mean"])
    rows += [
        ["FLNET2023 · label flip", "Accuracy ↑", fmt(FL["none"], "accuracy"),
         fmt(FL["v1"], "accuracy"), fmt(FL["v2"], "accuracy"), fmt(FL["v2_mondrian"], "accuracy")],
        ["FLNET2023 · label flip", "Honest excluded ↓", "—",
         fmt(FL["v1"], "false_positive_rate"), fmt(FL["v2"], "false_positive_rate"),
         fmt(FL["v2_mondrian"], "false_positive_rate")],
        ["NSL-KDD · label flip", "Accuracy ↑", fmt(NL["none"], "accuracy"),
         fmt(NL["v1"], "accuracy"), fmt(NL["v2"], "accuracy"), fmt(NL["v2_mondrian"], "accuracy")],
        ["NSL-KDD · label flip", "Honest excluded ↓", "—",
         fmt(NL["v1"], "false_positive_rate"), fmt(NL["v2"], "false_positive_rate"),
         fmt(NL["v2_mondrian"], "false_positive_rate")],
        ["NSL-KDD · backdoor", "Backdoor success ↓", fmt(NB["none"], "backdoor_asr"),
         fmt(NB["v1"], "backdoor_asr"), fmt(NB["v2"], "backdoor_asr"),
         fmt(NB["v2_mondrian"], "backdoor_asr")],
    ]
    table(slide, LEFT, Inches(1.95), [Inches(2.75), Inches(2.0), Inches(1.75), Inches(1.75),
                                      Inches(1.75), Inches(1.73)], rows, size=12,
          row_h=Inches(0.55))
    text(slide, LEFT, Inches(5.45), CONTENT_W, Inches(1.4), [
        [("v1", {"bold": True, "size": 12}), (" drops every flagged update.   ", {"size": 12,
                                                                               "color": INK_SOFT}),
         ("v2", {"bold": True, "size": 12}),
         (" adds the second check and a 15% weight cap — fewer honest routers excluded, but on "
          "FLNET2023 the cap can shift weight from an honest large router to the attackers "
          "(one seed: 97.3% → 83.8%).", {"size": 12, "color": INK_SOFT})],
        [("FLNET2023: 5 seeds · NSL-KDD: 10 seeds · means shown.", {"size": 10.5,
                                                                    "color": MUTED})],
    ], spacing=1.3)
    notes(slide, "Across both datasets the protocol beats no defense. v2 cuts false alarms; "
                 "on NSL-KDD it is better than v1 on every measure, while on FLNET2023 the "
                 "weight cap has a real downside. Mondrian is never clearly better.")


# ---- 06 Conclusion

def s_answer(prs):
    slide = base(prs, "06 · Conclusion", "Answering the research question")
    text(slide, LEFT, Inches(1.95), CONTENT_W, Inches(0.9),
         "Do per-cluster (Mondrian) thresholds reduce false alarms on honest non-IID routers "
         "without missing attacks?", size=16, font=SERIF, color=INK_SOFT, italic=True)
    tests = [
        ("Protocol experiment · 15 seeds",
         f"Mondrian caught {pct(PG['mondrian']['detection_rate_mean'])}, global "
         f"{pct(PG['global']['detection_rate_mean'])} · p = 0.21"),
        ("Defense experiment · both datasets", "no significant difference · all p > 0.17"),
        ("Scalability · 10, 20, 40 clients", "no significant difference · all p ≥ 0.11"),
    ]
    for i, (name, res) in enumerate(tests):
        y = Inches(3.0) + i * Inches(0.75)
        text(slide, LEFT, y, Inches(4.5), Inches(0.6), name, size=13.5, bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
        text(slide, Inches(5.4), y, Inches(7.1), Inches(0.6), res, size=13.5, color=INK_SOFT,
             anchor=MSO_ANCHOR.MIDDLE)
        hrule(slide, LEFT, y + Inches(0.66), CONTENT_W, weight=0.5)
    rect(slide, LEFT, Inches(5.4), CONTENT_W, Inches(1.25), fill=ACCENT_SOFT, line=None,
         radius=0.06)
    text(slide, LEFT + Inches(0.35), Inches(5.4), Inches(11), Inches(1.25), [
        [("Answer: no.", {"bold": True, "size": 15, "color": ACCENT}),
         ("  Once scores are standardized within each round, a single global threshold "
          "already keeps false alarms low; Mondrian adds complexity without a measurable gain "
          "— and the 'too few clients per cluster' explanation did not hold up to 40 clients.",
          {"size": 13})],
    ], anchor=MSO_ANCHOR.MIDDLE, spacing=1.3)
    notes(slide, "We tested the question three separate ways. Mondrian was never "
                 "significantly better. A negative answer, tested properly, is still an "
                 "answer — and it tells practitioners the simpler option is enough.")


def s_limits(prs):
    slide = base(prs, "06 · Conclusion", "What did not work, and limitations")
    items = [
        ("Binary detection was too easy.", "One feature scores 97.5% on FLNET2023 — so binary "
         "accuracy cannot separate setups."),
        ("First protocol design failed.", "Fixed thresholds flagged 65–96% of honest updates "
         "once training converged; fixed by per-round standardization."),
        ("The weight cap is not free.", "It can hand an honest large router's weight to the "
         "attackers."),
        ("Heavy dropout weakens the filter.", "At 40% offline, only about a third of poisoned "
         "updates are caught."),
        ("Evaluation limits.", "Simulated federation, emulated traffic, non-adaptive "
         "attackers, 5 seeds on FLNET2023."),
    ]
    bullets(slide, LEFT, Inches(2.0), Inches(11.5), Inches(4.8), items, size=14, gap=14)
    notes(slide, "We report what did not work as clearly as what did. Each of these is "
                 "documented in the README with the measurements behind it.")


def s_conclusion(prs):
    slide = base(prs, "06 · Conclusion", "Conclusion and future work")
    text(slide, LEFT, Inches(1.95), Inches(5.7), Inches(0.35), "CONCLUSIONS", size=11,
         bold=True, color=ACCENT)
    bullets(slide, LEFT, Inches(2.4), Inches(5.7), Inches(4.4), [
        "Federated training over 10 real routers matches centralized binary detection.",
        "Naming the attack exposes the non-IID cost: macro-F1 0.39 vs 0.76 IID.",
        "Krypsis rejects every tampered message and raises accuracy under attack at under 1% "
        "message cost.",
        "A global threshold is enough — Mondrian brought no significant gain.",
    ], size=14, gap=14)
    text(slide, Inches(7.0), Inches(1.95), Inches(5.5), Inches(0.35), "FUTURE WORK",
         size=11, bold=True, color=ACCENT)
    bullets(slide, Inches(7.0), Inches(2.4), Inches(5.5), Inches(4.4), [
        "Run the protocol on the multi-class task, where honest routers truly disagree.",
        "A trust-dependent weight cap instead of a fixed one.",
        "Score against a longer history to survive heavy dropout.",
        "Deploy over a real network (Mininet / SDN) and test adaptive attackers.",
        "More FLNET2023 seeds for statistical power.",
    ], size=14, gap=14)
    notes(slide, "Four conclusions and five next steps. The most valuable next step is the "
                 "multi-class protocol experiment, where honest routers genuinely disagree.")


def s_references(prs):
    slide = base(prs, "06 · Conclusion", "References")
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
        y = Inches(1.85) + row * Inches(0.84)
        box = text(slide, x, y, col_w, Inches(0.8),
                   [[(f"[{i + 1}]  ", {"color": ACCENT, "bold": True, "size": 10}),
                     (cite, {"size": 10})],
                    [(url, {"size": 9.5, "color": ACCENT})]], spacing=1.1)
        run = box.text_frame.paragraphs[1].runs[0]
        run.hyperlink.address = url
    text(slide, LEFT, Inches(6.75), CONTENT_W, Inches(0.25),
         "Code, results and full write-up: github.com/Vinudharshini18/Krypsis-A-network-intrusion-detection-system",
         size=9.5, color=MUTED)
    notes(slide, "All links are clickable in the slide. The GitHub repository has the code, "
                 "every result file, and the full README.")


def s_thanks(prs):
    slide = base(prs, bg=BG_DEEP, footer=False)
    text(slide, LEFT, Inches(2.6), Inches(11), Inches(1.2), "Thank you", size=60, font=SERIF)
    hrule(slide, LEFT, Inches(3.85), Inches(0.8), color=ACCENT, weight=1.5)
    text(slide, LEFT, Inches(4.05), Inches(11), Inches(0.6), "Questions and discussion",
         size=20, font=SERIF, color=INK_SOFT)
    text(slide, LEFT, Inches(5.6), Inches(11), Inches(0.4),
         "github.com/Vinudharshini18/Krypsis-A-network-intrusion-detection-system",
         size=12, color=ACCENT)
    notes(slide, "Thank the panel and open for questions. The handbook has prepared answers "
                 "for the likely ones: why 100% accuracy, and why the research question came "
                 "out negative.")


def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    s_title(prs)
    s_outline(prs)
    divider(prs, "01", "Introduction", "Why intrusion detection needs federated learning — "
                                       "and why that is not the end of the problem")
    s_background(prs)
    s_fl(prs)
    s_gap(prs)
    s_question(prs)
    divider(prs, "02", "Objectives", "What we set out to do, and the scope we did it in")
    s_objectives(prs)
    s_scope(prs)
    divider(prs, "03", "Methodology", "Data, model, the Krypsis protocol and how we tested it")
    s_architecture(prs)
    s_dataset(prs)
    s_preprocess(prs)
    s_model(prs)
    s_message(prs)
    s_server(prs)
    s_design(prs)
    divider(prs, "04", "Results", "Detection, attacks, backdoors and robustness")
    s_baseline(prs)
    s_multiclass(prs)
    s_attack(prs)
    s_backdoor(prs)
    s_dropout(prs)
    s_scale(prs)
    divider(prs, "05", "Comparison", "Against existing approaches, and between our own setups")
    s_compare_existing(prs)
    s_compare_ours(prs)
    divider(prs, "06", "Conclusion", "The answer to our question, limitations and what comes next")
    s_answer(prs)
    s_limits(prs)
    s_conclusion(prs)
    s_references(prs)
    s_thanks(prs)
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
