"""
Figures for the README and the slides, drawn from results/*.json.

Writes PNGs to results/figures/. A figure whose results file does not exist
yet is skipped, so this can be re-run after any experiment.

Colours: the first three slots of a colour-blind-validated categorical
palette (blue, orange, aqua), always in that order, and every series is
also named by a direct label or legend, never by colour alone.

Run: venv\\Scripts\\python.exe src\\make_plots.py
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
FIG_DIR = os.path.join(RESULTS_DIR, "figures")

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]      # blue, orange, aqua
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3df"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_SOFT, "axes.titlecolor": INK,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.labelsize": 10.5, "xtick.color": INK_SOFT, "ytick.color": INK_SOFT,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "legend.fontsize": 9.5, "font.family": "DejaVu Sans",
    "lines.linewidth": 2, "lines.markersize": 6,
})


def load(name):
    path = os.path.join(RESULTS_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save(fig, name, note=None):
    if note:
        fig.text(0.01, -0.02, note, fontsize=8.5, color=INK_SOFT, ha="left", va="top")
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"  {name}")


def end_label(ax, x, y, text, color, dy=0.0):
    ax.annotate(text, (x, y), xytext=(6, dy), textcoords="offset points",
                color=INK, fontsize=9.5, va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec=color, lw=1.2))


def bar_labels(ax, bars, fmt, errs=None):
    for i, b in enumerate(bars):
        v = b.get_height()
        top = v + (errs[i] if errs else 0)
        ax.annotate(fmt(v), (b.get_x() + b.get_width() / 2, top), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=9, color=INK)


def fig_attack_accuracy(defense):
    """Accuracy by round under label flipping: none / v1 / v2, per dataset."""
    if not defense:
        return
    runs = defense["runs"]
    calib = defense["config"]["calibration_rounds"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, (ds, title) in zip(axes, (("nslkdd", "NSL-KDD"), ("flnet", "FLNET2023"))):
        ends = []
        for color, (policy, label) in zip(SERIES, (("none", "No defense"),
                                                   ("v1", "Protocol v1"),
                                                   ("v2", "Protocol v2"))):
            rs = [r for r in runs if r["dataset"] == ds and r["attack"] == "label_flip"
                  and r["policy"] == policy]
            if not rs:
                continue
            curve = 100 * np.mean([[h["accuracy"] for h in r["by_round"]] for r in rs], axis=0)
            rounds = np.arange(1, len(curve) + 1)
            ax.plot(rounds, curve, color=color, marker="o", label=label)
            ends.append((curve[-1], label, color, rounds[-1]))
        # spread end labels so they do not collide
        ends.sort()
        last = -1e9
        for value, label, color, x in ends:
            y = max(value, last + 2.2)
            end_label(ax, x, y, f"{label} {value:.1f}%", color)
            last = y
        ax.axvspan(0.5, calib + 0.5, color=GRID, alpha=0.45, lw=0)
        ax.text(calib / 2 + 0.5, ax.get_ylim()[0], "clean\ncalibration", ha="center",
                va="bottom", fontsize=8.5, color=INK_SOFT)
        ax.axvline(calib + 0.5, color=INK_SOFT, lw=1, ls="--")
        ax.set_title(f"{title}: accuracy under label flipping")
        ax.set_xlabel("Training round (attack starts after the dashed line)")
        ax.set_ylabel("Test accuracy (%)")
        ax.set_xlim(0.5, rounds[-1] + 4.5)
        ax.set_xticks(range(1, rounds[-1] + 1))
    seeds = defense["config"].get("seeds_per_dataset", {})
    save(fig, "attack_accuracy_by_round.png",
         f"Mean over seeds (NSL-KDD {seeds.get('nslkdd', '?')}, FLNET2023 {seeds.get('flnet', '?')}); "
         "2 of 10 clients attack.")


def fig_backdoor(defense):
    if not defense:
        return
    s = defense["summary"].get("nslkdd/backdoor")
    if not s:
        return
    labels = ["No defense", "Protocol v1", "Protocol v2"]
    vals = [100 * s[p]["backdoor_asr_mean"] for p in ("none", "v1", "v2")]
    errs = [100 * s[p]["backdoor_asr_std"] for p in ("none", "v1", "v2")]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, vals, color=SERIES[0], width=0.55, yerr=errs,
                  error_kw=dict(ecolor=INK_SOFT, lw=1, capsize=4))
    bar_labels(ax, bars, lambda v: f"{v:.1f}%", errs)
    ax.set_title("NSL-KDD backdoor: attack success rate")
    ax.set_ylabel("satan attacks let through (%) — lower is better")
    ax.grid(axis="x", visible=False)
    save(fig, "backdoor_success.png", "Mean ± std over 10 seeds.")


def fig_multiclass(mc):
    if not mc:
        return
    classes = mc["classes"]
    setups = (("centralized", "Centralized"), ("federated_iid", "FedAvg, IID"),
              ("federated_router", "FedAvg, real routers"))
    y = np.arange(len(classes))
    h = 0.26
    fig, ax = plt.subplots(figsize=(9, 6.2))
    for i, (key, label) in enumerate(setups):
        vals = [100 * mc[key]["per_class_recall"][c] for c in classes]
        ax.barh(y + (i - 1) * h, vals, height=h - 0.03, color=SERIES[i],
                label=f"{label} (macro-F1 {mc[key]['macro_f1']:.2f})")
        for yi, v in zip(y, vals):
            if v < 0.5:
                ax.text(0.8, yi + (i - 1) * h, "0%", va="center", fontsize=8, color=INK)
    ax.set_yticks(y, classes)
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("Recall per traffic type (%)")
    ax.set_title("Multi-class detection: which traffic types are learned")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3)
    save(fig, "multiclass_recall.png")


def fig_message_size(protocol):
    if not protocol:
        return
    c = protocol["communication"]
    labels = ["Raw update", "Krypsis message", "HTTP / JSON"]
    vals = [c["raw_payload_bytes"] / 1000, c["krypsis_message_bytes"] / 1000,
            c["http_json_bytes"] / 1000]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    bars = ax.barh(labels, vals, color=SERIES[0], height=0.5)
    for b, v in zip(bars, vals):
        ax.annotate(f"{v:,.0f} KB", (v, b.get_y() + b.get_height() / 2), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=9.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.18)
    ax.set_xlabel("Size of one model update (KB)")
    ax.set_title("Message size per update")
    ax.grid(axis="y", visible=False)
    save(fig, "message_size.png",
         f"Krypsis adds {c['krypsis_overhead_bytes']:,} B "
         f"({100 * c['krypsis_overhead_bytes'] / c['raw_payload_bytes']:.2f}%) for header, fingerprint and tag.")


def fig_dropout(robust):
    if not robust or "dropout" not in robust["summary"]:
        return
    s = robust["summary"]["dropout"]
    rates = sorted(s, key=float)
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for color, (policy, label) in zip(SERIES, (("none", "No defense"), ("v2", "Protocol v2"))):
        xs = [100 * float(r) for r in rates if policy in s[r]]
        ys = [100 * s[r][policy]["final_accuracy_mean"] for r in rates if policy in s[r]]
        if xs:
            ax.plot(xs, ys, color=color, marker="o", label=label)
            end_label(ax, xs[-1], ys[-1], f"{label} {ys[-1]:.1f}%", color)
    ax.set_xticks([100 * float(r) for r in rates])
    ax.set_xlim(-5, 100 * float(rates[-1]) + 22)
    ax.set_xlabel("Chance each router is offline in a round (%)")
    ax.set_ylabel("Final test accuracy (%)")
    ax.set_title("Client dropout under label flipping (FLNET2023)")
    save(fig, "dropout_accuracy.png", f"Mean over {robust['config']['num_seeds']} seeds; 2 of 10 routers attack.")


def fig_scale(robust):
    if not robust or "scale" not in robust["summary"]:
        return
    s = robust["summary"]["scale"]
    ks = sorted(s, key=int)
    clients = [10 * int(k) for k in ks]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, (metric, title, ylabel) in zip(axes, (
            ("detection_rate", "Poisoned updates caught", "Caught (%) — higher is better"),
            ("false_positive_rate", "Honest updates wrongly excluded", "Excluded (%) — lower is better"))):
        for color, (policy, label) in zip(SERIES, (("v2", "Global threshold"),
                                                   ("v2_mondrian", "Mondrian thresholds"))):
            ys = [100 * s[k][policy][f"{metric}_mean"] for k in ks if policy in s[k]]
            if ys:
                ax.plot(clients[:len(ys)], ys, color=color, marker="o", label=label)
        ax.set_xticks(clients)
        ax.set_xlabel("Number of clients (each router split into sub-clients)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(loc="best")
    save(fig, "scale_global_vs_mondrian.png",
         f"FLNET2023, 20% of clients attack, mean over {robust['config']['num_seeds']} seeds.")


def fig_shift(robust):
    if not robust or "shift" not in robust["summary"]:
        return
    s = list(robust["summary"]["shift"].values())[0]
    cfg = robust["config"]["shift"]
    labels, vals_shift, vals_other = [], [], []
    for policy, label in (("v2", "Global threshold"), ("v2_mondrian", "Mondrian thresholds")):
        if policy in s:
            labels.append(label)
            vals_shift.append(100 * s[policy].get("shifted_client_excluded_rate_mean", 0))
            vals_other.append(100 * s[policy].get("other_honest_excluded_after_shift_mean", 0))
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(6.5, 4))
    b1 = ax.bar(x - 0.18, vals_shift, width=0.34, color=SERIES[0],
                label=f"Router {cfg['router']} (traffic changed)")
    b2 = ax.bar(x + 0.18, vals_other, width=0.34, color=SERIES[1], label="Other honest routers")
    bar_labels(ax, list(b1) + list(b2), lambda v: f"{v:.1f}%")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Updates wrongly excluded (%)")
    ax.set_title(f"Honest router starts seeing {cfg['type']}")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    save(fig, "distribution_shift.png", f"FLNET2023, no attackers, shift after round {cfg['round']}.")


def main():
    print(f"Writing figures to {FIG_DIR}")
    defense = load("defense_experiment.json")
    fig_attack_accuracy(defense)
    fig_backdoor(defense)
    fig_multiclass(load("multiclass.json"))
    fig_message_size(load("protocol_experiment.json"))
    robust = load("robustness_experiment.json")
    fig_dropout(robust)
    fig_scale(robust)
    fig_shift(robust)


if __name__ == "__main__":
    main()
