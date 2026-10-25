"""
Centralized baseline and FedAvg on the 70 / 15 / 15 split (see
src/split_701515.py), with an overfitting check.

  - train (70%):      the model learns from it (each router only its own part)
  - validation (15%): early stopping, decision-threshold tuning, and the
                      per-epoch / per-round curves
  - test (15%):       used once, at the end, for the reported numbers
  - capture:          the dataset's separate TEST capture (flows already in
                      our data removed), an extra "new traffic" check

Train, validation and test accuracy and loss are reported side by side: if
they are close, the model is not overfitting.

Results go to results/split_701515/; earlier results are not touched.

Run: venv\\Scripts\\python.exe src\\split_experiment.py [centralized] [router] [iid]
     (no arguments = all three)
"""

import json
import os
import sys
import time

import numpy as np
import tensorflow as tf
from sklearn.utils.class_weight import compute_class_weight

from federated_training import BATCH_SIZE, LOCAL_EPOCHS, NUM_ROUNDS, federated_average
from model import build_model, evaluate, tune_threshold

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "processed_701515")
OUT_DIR = os.path.join(PROJECT_ROOT, "results", "split_701515")
SETS = ("train", "val", "test", "capture")


def load():
    d = {}
    for s in SETS:
        d[f"X_{s}"] = np.load(os.path.join(DATA_DIR, f"X_{s}.npy"))
        d[f"y_{s}"] = np.load(os.path.join(DATA_DIR, f"y_{s}.npy"))
    d["test_client"] = np.load(os.path.join(DATA_DIR, "test_client.npy"))
    return d


def loss_of(model, X, y):
    # model.evaluate runs without dropout, so train and test loss are comparable.
    return float(model.evaluate(X, y, batch_size=4096, verbose=0)[0])


def full_report(model, d, threshold):
    out = {"threshold": threshold}
    for s in SETS:
        m = evaluate(model, d[f"X_{s}"], d[f"y_{s}"], threshold=threshold)
        m["loss"] = loss_of(model, d[f"X_{s}"], d[f"y_{s}"])
        out[s] = m
    prob = model.predict(d["X_test"], verbose=0).ravel()
    pred = (prob >= threshold).astype(int)
    out["test_accuracy_per_router"] = {
        int(c) + 1: float((pred[d["test_client"] == c] == d["y_test"][d["test_client"] == c]).mean())
        for c in np.unique(d["test_client"])}
    out["train_test_accuracy_gap"] = out["train"]["accuracy"] - out["test"]["accuracy"]
    return out


def print_table(name, r):
    print(f"\n{name}: threshold {r['threshold']}")
    print(f"  {'set':8s} {'accuracy':>9s} {'precision':>9s} {'recall':>9s} {'f1':>9s} {'loss':>8s}")
    for s in SETS:
        m = r[s]
        print(f"  {s:8s} {m['accuracy']:9.4f} {m['precision']:9.4f} {m['recall']:9.4f} "
              f"{m['f1_score']:9.4f} {m['loss']:8.4f}")
    print(f"  train - test accuracy gap: {100 * r['train_test_accuracy_gap']:+.2f} points")


def save(name, obj):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{name}.json"), "w") as f:
        json.dump(obj, f, indent=2)


def run_centralized(d, epochs=80):
    t0 = time.time()
    weights = compute_class_weight("balanced", classes=np.array([0, 1]), y=d["y_train"])
    print(f"\n=== Centralized: {len(d['y_train'])} train, {len(d['y_val'])} validation flows ===")
    model = build_model(d["X_train"].shape[1])
    hist = model.fit(
        d["X_train"], d["y_train"], epochs=epochs, batch_size=256,
        validation_data=(d["X_val"], d["y_val"]),
        class_weight={0: weights[0], 1: weights[1]},
        callbacks=[tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=10, restore_best_weights=True)],
        verbose=2)
    threshold = tune_threshold(model, d["X_val"], d["y_val"])
    r = full_report(model, d, threshold)
    r["epochs_run"] = len(hist.history["loss"])
    r["best_epoch"] = int(np.argmin(hist.history["val_loss"])) + 1
    r["curves"] = {k: [float(v) for v in vals] for k, vals in hist.history.items()}
    r["minutes"] = round((time.time() - t0) / 60, 1)
    print_table("Centralized", r)
    save("centralized", r)
    return r


def run_federated(d, split):
    t0 = time.time()
    assignment = np.load(os.path.join(DATA_DIR, f"client_assignment_{split}.npy"))
    clients = np.unique(assignment)
    print(f"\n=== FedAvg, {split} split, {len(clients)} clients, {NUM_ROUNDS} rounds ===")
    global_model = build_model(d["X_train"].shape[1])
    weights = global_model.get_weights()
    curves = []
    for rnd in range(1, NUM_ROUNDS + 1):
        local, counts = [], []
        for c in clients:
            mask = assignment == c
            m = build_model(d["X_train"].shape[1])
            m.set_weights(weights)
            m.fit(d["X_train"][mask], d["y_train"][mask], epochs=LOCAL_EPOCHS,
                  batch_size=BATCH_SIZE, verbose=0)
            local.append(m.get_weights())
            counts.append(int(mask.sum()))
        weights = federated_average(local, counts)
        global_model.set_weights(weights)
        point = {"round": rnd,
                 "train_loss": loss_of(global_model, d["X_train"], d["y_train"]),
                 "val_loss": loss_of(global_model, d["X_val"], d["y_val"]),
                 "train_accuracy": evaluate(global_model, d["X_train"], d["y_train"])["accuracy"],
                 "val_accuracy": evaluate(global_model, d["X_val"], d["y_val"])["accuracy"]}
        curves.append(point)
        print(f"  round {rnd:2d}: train acc {point['train_accuracy']:.4f}  "
              f"val acc {point['val_accuracy']:.4f}  "
              f"train loss {point['train_loss']:.4f}  val loss {point['val_loss']:.4f}",
              flush=True)
    threshold = tune_threshold(global_model, d["X_val"], d["y_val"])
    r = full_report(global_model, d, threshold)
    r["curves"] = curves
    r["minutes"] = round((time.time() - t0) / 60, 1)
    print_table(f"FedAvg ({split})", r)
    save(f"federated_{split}", r)
    return r


def plot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = []
    for name, title in (("centralized", "Centralized"), ("federated_router", "FedAvg, router split"),
                        ("federated_iid", "FedAvg, IID split")):
        path = os.path.join(OUT_DIR, f"{name}.json")
        if os.path.exists(path):
            with open(path) as f:
                panels.append((title, json.load(f)))
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
    os.makedirs(os.path.join(OUT_DIR, "figures"), exist_ok=True)
    fig.savefig(os.path.join(OUT_DIR, "figures", "loss_curves.png"), dpi=150)
    print(f"Saved {os.path.join(OUT_DIR, 'figures', 'loss_curves.png')}")


def main():
    parts = sys.argv[1:] or ["centralized", "router", "iid"]
    d = load()
    print({s: len(d[f"y_{s}"]) for s in SETS})
    if "centralized" in parts:
        run_centralized(d)
    for split in ("router", "iid"):
        if split in parts:
            run_federated(d, split)
    plot()


if __name__ == "__main__":
    main()
