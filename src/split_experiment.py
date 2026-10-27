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

The three stages can also be run one at a time:
  src/train_model.py   -> trains, saves models to results/split_701515/models/
  src/test_model.py    -> loads the saved models, evaluates, saves *.json
  src/show_results.py  -> prints the tables and draws the loss curves

Results go to results/split_701515/; earlier results are not touched.

Run all three stages: venv\\Scripts\\python.exe src\\split_experiment.py [centralized] [router] [iid]
     (no arguments = all three models)
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
MODEL_DIR = os.path.join(OUT_DIR, "models")
SETS = ("train", "val", "test", "capture")
# name of each model -> how it is trained
MODELS = {"centralized": "centralized", "router": "federated_router", "iid": "federated_iid"}
TITLES = {"centralized": "Centralized", "federated_router": "FedAvg, router split",
          "federated_iid": "FedAvg, IID split"}


def parts_from_args(argv):
    parts = [a for a in argv if a in MODELS] or list(MODELS)
    return [MODELS[p] for p in parts]


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


# ------------------------------------------------------------------ training

def train_centralized(d, epochs=80):
    """Train on the 70% set, early stopping and threshold on validation.
    Returns (model, info)."""
    t0 = time.time()
    weights = compute_class_weight("balanced", classes=np.array([0, 1]), y=d["y_train"])
    print(f"\n=== Training centralized: {len(d['y_train'])} train, "
          f"{len(d['y_val'])} validation flows ===")
    model = build_model(d["X_train"].shape[1])
    hist = model.fit(
        d["X_train"], d["y_train"], epochs=epochs, batch_size=256,
        validation_data=(d["X_val"], d["y_val"]),
        class_weight={0: weights[0], 1: weights[1]},
        callbacks=[tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=10, restore_best_weights=True)],
        verbose=2)
    info = {"threshold": tune_threshold(model, d["X_val"], d["y_val"]),
            "epochs_run": len(hist.history["loss"]),
            "best_epoch": int(np.argmin(hist.history["val_loss"])) + 1,
            "curves": {k: [float(v) for v in vals] for k, vals in hist.history.items()},
            "minutes": round((time.time() - t0) / 60, 1)}
    print(f"  stopped after {info['epochs_run']} epochs, kept epoch {info['best_epoch']}, "
          f"threshold {info['threshold']}, {info['minutes']} min")
    return model, info


def train_federated(d, split):
    """FedAvg over the training set's clients; validation curves every round,
    threshold tuned on validation at the end. Returns (model, info)."""
    t0 = time.time()
    assignment = np.load(os.path.join(DATA_DIR, f"client_assignment_{split}.npy"))
    clients = np.unique(assignment)
    print(f"\n=== Training FedAvg, {split} split, {len(clients)} clients, "
          f"{NUM_ROUNDS} rounds ===")
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
    info = {"threshold": tune_threshold(global_model, d["X_val"], d["y_val"]),
            "curves": curves, "minutes": round((time.time() - t0) / 60, 1)}
    print(f"  threshold {info['threshold']}, {info['minutes']} min")
    return global_model, info


def train_one(d, name):
    if name == "centralized":
        return train_centralized(d)
    return train_federated(d, name.replace("federated_", ""))


def save_model(name, model, info):
    os.makedirs(MODEL_DIR, exist_ok=True)
    model.save(os.path.join(MODEL_DIR, f"{name}.keras"))
    with open(os.path.join(MODEL_DIR, f"{name}_info.json"), "w") as f:
        json.dump(info, f, indent=2)
    print(f"  saved model to {os.path.join(MODEL_DIR, name + '.keras')}")


def load_model(name):
    path = os.path.join(MODEL_DIR, f"{name}.keras")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No trained model at {path} - run src\\train_model.py first.")
    with open(os.path.join(MODEL_DIR, f"{name}_info.json")) as f:
        info = json.load(f)
    # Testing needs the weights, not the training state of the optimizer.
    model = tf.keras.models.load_model(path, compile=False)
    model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
    return model, info


# ------------------------------------------------------------------ testing

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


def test_one(d, name, model, info):
    """Evaluate a trained model on every set and save results/<name>.json."""
    print(f"\n=== Testing {TITLES[name]} ===")
    r = full_report(model, d, info["threshold"])
    r.update({k: v for k, v in info.items() if k != "threshold"})
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{name}.json"), "w") as f:
        json.dump(r, f, indent=2)
    print_table(TITLES[name], r)
    return r


# ------------------------------------------------------------------ results

def print_table(title, r):
    print(f"\n{title}: decision threshold {r['threshold']}")
    print(f"  {'set':8s} {'accuracy':>9s} {'precision':>9s} {'recall':>9s} {'f1':>9s} {'loss':>8s}")
    for s in SETS:
        m = r[s]
        print(f"  {s:8s} {m['accuracy']:9.4f} {m['precision']:9.4f} {m['recall']:9.4f} "
              f"{m['f1_score']:9.4f} {m['loss']:8.4f}")
    print(f"  train - test accuracy gap: {100 * r['train_test_accuracy_gap']:+.2f} points")


def plot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = []
    for name in MODELS.values():
        path = os.path.join(OUT_DIR, f"{name}.json")
        if os.path.exists(path):
            with open(path) as f:
                panels.append((TITLES[name], json.load(f)))
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
    names = parts_from_args(sys.argv[1:])
    d = load()
    print({s: len(d[f"y_{s}"]) for s in SETS})
    for name in names:
        model, info = train_one(d, name)
        save_model(name, model, info)
        test_one(d, name, model, info)
    plot()


if __name__ == "__main__":
    main()
