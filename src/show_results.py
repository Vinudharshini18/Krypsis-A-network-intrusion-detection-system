"""
Step 3 of 3 - RESULTS (70 / 15 / 15 split).

Reads the saved results (no training, no TensorFlow needed).

Default: a short summary - detection accuracy / precision / recall / F1,
the overfitting check, Krypsis under attack, tampered messages.

--details: all tables - before vs after the split, train / validation /
test for every model, per-router accuracy, the extra overfitting checks,
the attack experiments - and redraws
results/split_701515/figures/loss_curves.png.

Run: venv\\Scripts\\python.exe src\\show_results.py [--details]
"""

import json
import os
import sys

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PROJECT_ROOT, "results", "split_701515")
SETS = ("train", "val", "test", "capture")
TITLES = {"centralized": "Centralized", "federated_router": "FedAvg, router split",
          "federated_iid": "FedAvg, IID split"}


def read(name):
    path = os.path.join(OUT_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def summary():
    """The short version: the four results to show."""
    fr, cen = read("federated_router.json"), read("centralized.json")
    cv, loro = read("overfitting_checks/cv.json"), read("overfitting_checks/loro.json")
    shuffle = read("overfitting_checks/shuffle.json")
    prot, defense = read("protocol_experiment.json"), read("defense_experiment.json")
    line = "=" * 66
    print(line)
    print("  KRYPSIS - FINAL RESULTS")
    print("  FLNET2023, 10 routers, 70/15/15 split, duplicates removed")
    print(line)

    if fr:
        t = fr["test"]
        (tn, fp), (fn, tp) = t["confusion_matrix"]
        print("\n1. DETECTING ATTACKS  (FedAvg over 10 routers, test set)")
        print(f"   Accuracy  {100 * t['accuracy']:6.2f}%     Precision {100 * t['precision']:6.2f}%")
        print(f"   Recall    {100 * t['recall']:6.2f}%     F1 score  {100 * t['f1_score']:6.2f}%")
        print(f"   Mistakes: {fp + fn} of {tn + fp + fn + tp:,} flows "
              f"({fp} false alarms, {fn} missed attacks)")
        if cen:
            print(f"   Centralized model (all data in one place): {100 * cen['test']['accuracy']:.2f}%")

        print("\n2. OVERFITTING CHECK  ->  ", end="")
        gap = 100 * fr["train_test_accuracy_gap"]
        print("NO overfitting" if abs(gap) < 0.5 else "possible overfitting")
        print(f"   Train {100 * fr['train']['accuracy']:.2f}%  |  Validation "
              f"{100 * fr['val']['accuracy']:.2f}%  |  Test {100 * fr['test']['accuracy']:.2f}%"
              f"   (gap {gap:+.2f})")
        if cv and "test_accuracy_mean" in cv:
            lo = min(f["test"]["accuracy"] for f in cv["folds"])
            print(f"   5-fold cross-validation: {100 * cv['test_accuracy_mean']:.2f}% on average, "
                  f"lowest fold {100 * lo:.2f}%")
        if loro:
            accs = [v["unseen_router"]["accuracy"] for v in loro.values()]
            print(f"   Router never seen in training: {100 * min(accs):.2f}% to "
                  f"{100 * max(accs):.2f}% ({len(accs)} routers)")
        if shuffle:
            b = shuffle["test_with_real_labels"]["balanced_accuracy"]
            print(f"   Shuffled labels: {100 * b:.1f}% balanced accuracy = guessing "
                  f"-> no data leak")

    fl = defense["summary"].get("flnet/label_flip") if defense else None
    if fl:
        print("\n3. KRYPSIS PROTECTING THE MODEL  (2 of 10 routers poisoned)")
        rows = (("No protection", "none", ""),
                ("Krypsis v1", "v1", "throws suspicious updates away"),
                ("Krypsis v2, global", "v2", "+ second check + 15% cap, one limit"),
                ("Krypsis v2, Mondrian", "v2_mondrian", "+ one limit per group  <- BEST"))
        for name, key, note in rows:
            v = fl[key]
            extra = ("" if key == "none" else
                     f"  caught {100 * v['detection_rate_mean']:4.1f}%")
            print(f"   {name:21s} accuracy {100 * v['accuracy_mean']:6.2f}%{extra}   {note}")
        m = fl["v2_mondrian"]
        print(f"   Honest updates lost with v2 Mondrian: {100 * m['false_positive_rate_mean']:.1f}%")

    if prot:
        g, comm = prot["summary"]["global"], prot["communication"]
        print("\n4. TAMPERED MESSAGES")
        print(f"   Rejected: {g['tamper_rejected']} / {g['tamper_sent']} "
              f"({100 * g['tamper_rejected'] / g['tamper_sent']:.0f}%)")
        print(f"   Message size cost: +{100 * comm['krypsis_overhead_bytes'] / comm['raw_payload_bytes']:.2f}%")
    print("\n" + line)
    print("  Full tables: venv\\Scripts\\python.exe src\\show_results.py --details")
    print(line)


def read_old(name):
    path = os.path.join(PROJECT_ROOT, "results", name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        r = json.load(f)
    return r[-1] if isinstance(r, list) else r


def before_after():
    print("=" * 78)
    print("0. TEST SET: BEFORE (old 88/12 split) vs AFTER (70/15/15, duplicates removed)")
    print("=" * 78)
    print(f"  {'model':16s} {'':7s} {'accuracy':>9s} {'precision':>9s} {'recall':>8s} "
          f"{'f1':>8s} {'false alarm':>11s} {'missed':>7s} {'flows':>7s}")
    pairs = (("Centralized", "centralized_baseline.json", "centralized.json"),
             ("FedAvg routers", "federated_router.json", "federated_router.json"),
             ("FedAvg IID", "federated_iid.json", "federated_iid.json"))
    for title, old_name, new_name in pairs:
        new = read(new_name)
        for tag, m in (("before", read_old(old_name)), ("after", new["test"] if new else None)):
            if m is None:
                continue
            (tn, fp), (fn, tp) = m["confusion_matrix"]
            print(f"  {title if tag == 'before' else '':16s} {tag:7s} {100 * m['accuracy']:9.3f} "
                  f"{100 * m['precision']:9.3f} {100 * m['recall']:8.3f} {100 * m['f1_score']:8.3f} "
                  f"{fp:11d} {fn:7d} {tn + fp + fn + tp:7d}")
    print("  (%; false alarm = normal called attack, missed = attack called normal)\n")


def overfitting():
    print("=" * 70)
    print("1. OVERFITTING CHECK  (accuracy, %)")
    print("=" * 70)
    print(f"  {'model':24s} {'train':>8s} {'valid.':>8s} {'test':>8s} {'capture':>8s} {'gap':>8s}")
    found = False
    for name, title in TITLES.items():
        r = read(f"{name}.json")
        if r is None:
            continue
        found = True
        acc = [100 * r[s]["accuracy"] for s in SETS]
        print(f"  {title:24s} " + " ".join(f"{a:8.2f}" for a in acc)
              + f" {100 * r['train_test_accuracy_gap']:+8.2f}")
    if not found:
        print("  no results yet - run src\\train_model.py and src\\test_model.py")
        return
    print("  gap = train - test. Near 0 means the model is not overfitting.")

    r = read("federated_router.json")
    if r:
        print("\n2. FedAvg TEST ACCURACY PER ROUTER  (%)")
        print("  " + "  ".join(f"R{k}: {100 * v:.2f}" for k, v in r["test_accuracy_per_router"].items()))


def extra_checks():
    cv, loro = read("overfitting_checks/cv.json"), read("overfitting_checks/loro.json")
    shuffle, curve = read("overfitting_checks/shuffle.json"), read("overfitting_checks/curve.json")
    if not any((cv, loro, shuffle, curve)):
        return
    print("\n" + "=" * 70)
    print("EXTRA OVERFITTING CHECKS  (src/overfitting_checks.py)")
    print("=" * 70)
    if cv:
        print("  a) 5-fold cross-validation  (accuracy, %)")
        for f in cv["folds"]:
            print(f"     fold {f['fold']}: train {100 * f['train']['accuracy']:.2f}   "
                  f"test {100 * f['test']['accuracy']:.2f}   ({f['test']['errors']} errors "
                  f"in {f['test']['flows']:,} flows)")
        if "test_accuracy_mean" in cv:
            print(f"     mean test {100 * cv['test_accuracy_mean']:.2f} "
                  f"+/- {100 * cv['test_accuracy_std']:.2f}")
    if loro:
        print("  b) Leave-one-router-out: train on 9 routers, test on the unseen 10th")
        for r in sorted(loro, key=int):
            v = loro[r]
            print(f"     router {int(r):2d} unseen: accuracy {100 * v['unseen_router']['accuracy']:6.2f}   "
                  f"balanced {100 * v['unseen_router']['balanced_accuracy']:6.2f}   "
                  f"(train {100 * v['train']['accuracy']:.2f})")
    if shuffle:
        t = shuffle["test_with_real_labels"]
        print("  c) Shuffled labels (sanity check: should NOT learn anything)")
        print(f"     test accuracy {100 * t['accuracy']:.2f}  vs always-guess-attack "
              f"{100 * shuffle['always_attack_accuracy']:.2f};  balanced accuracy "
              f"{100 * t['balanced_accuracy']:.2f} (50 = guessing)")
    if curve:
        print("  d) Learning curve: share of training data used -> accuracy")
        for p in curve["points"]:
            print(f"     {100 * p['fraction']:5.1f}% ({p['train_flows']:7,} flows): "
                  f"train {100 * p['train']['accuracy']:.2f}   test {100 * p['test']['accuracy']:.2f}")


def attacks():
    prot, defense = read("protocol_experiment.json"), read("defense_experiment.json")
    if not prot and not defense:
        return
    print("\n" + "=" * 70)
    print("3. KRYPSIS UNDER LABEL-FLIPPING ATTACK  (2 of 10 routers)")
    print("=" * 70)
    if prot:
        runs, s = prot["runs"], prot["summary"]
        print(f"  Global vs Mondrian, {prot['config']['num_seeds']} seeds:")
        print(f"  {'':12s} {'acc rounds 6-12':>16s} {'last round':>11s} {'caught':>8s} {'honest flagged':>15s}")
        for pol in ("none", "global", "mondrian"):
            rs = [r for r in runs if r["policy"] == pol]
            avg = 100 * np.mean([np.mean(r["accuracy_by_round"][5:]) for r in rs])
            caught = "-" if pol == "none" else f"{100 * s[pol]['detection_rate_mean']:.1f}"
            fpr = "-" if pol == "none" else f"{100 * s[pol]['false_positive_rate_mean']:.1f}"
            print(f"  {pol:12s} {avg:16.1f} {100 * s[pol]['final_accuracy_mean']:11.1f} "
                  f"{caught:>8s} {fpr:>15s}")
        g = s["global"]
        print(f"  tampered messages rejected: {g['tamper_rejected']} / {g['tamper_sent']}")
    if defense:
        fl = defense["summary"].get("flnet/label_flip")
        if fl:
            print(f"\n  Krypsis v2 (second check + 15% cap), {fl['none']['runs']} seeds:")
            print(f"  {'':12s} {'accuracy':>9s} {'caught':>8s} {'honest excluded':>16s}")
            for pol in ("none", "v1", "v2", "v2_mondrian"):
                v = fl[pol]
                caught = "-" if pol == "none" else f"{100 * v['detection_rate_mean']:.1f}"
                fpr = "-" if pol == "none" else f"{100 * v['false_positive_rate_mean']:.1f}"
                print(f"  {pol:12s} {100 * v['accuracy_mean']:9.2f} {caught:>8s} {fpr:>16s}")


def main():
    if "--details" not in sys.argv[1:]:
        summary()
        return
    before_after()
    overfitting()
    extra_checks()
    attacks()
    plot()


def plot():
    """Redraw the train vs validation loss curves (matplotlib only)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = [(t, read(f"{n}.json")) for n, t in TITLES.items() if read(f"{n}.json")]
    if not panels:
        return
    fig, axes = plt.subplots(1, len(panels), figsize=(5 * len(panels), 3.6), squeeze=False)
    for ax, (title, r) in zip(axes[0], panels):
        if isinstance(r["curves"], dict):
            x = range(1, len(r["curves"]["loss"]) + 1)
            ax.plot(x, r["curves"]["loss"], label="train loss (with dropout)")
            ax.plot(x, r["curves"]["val_loss"], label="validation loss")
            ax.axvline(r["best_epoch"], color="grey", ls=":", lw=1, label="best epoch (kept)")
            ax.set_xlabel("epoch")
        else:
            x = [p["round"] for p in r["curves"]]
            ax.plot(x, [p["train_loss"] for p in r["curves"]], label="train loss")
            ax.plot(x, [p["val_loss"] for p in r["curves"]], label="validation loss")
            ax.set_xlabel("round")
        ax.set_title(title)
        ax.set_ylabel("loss")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "figures", "loss_curves.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=150)
    print(f"\nLoss-curve picture: {path}")


if __name__ == "__main__":
    main()
