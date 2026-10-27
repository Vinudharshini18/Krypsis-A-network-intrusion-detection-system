"""
Extra overfitting checks on the deduplicated FLNET2023 data (70 / 15 / 15
split from src/split_701515.py). Same MLP and training recipe as the
centralized model (class weights, early stopping on a validation part,
threshold tuned on validation).

  cv       5-fold cross-validation over all 393,409 unique flows
           (stratified by router and label). Same accuracy in every fold =
           the result does not depend on one lucky split.
  loro     leave-one-router-out: train on 9 routers, test on the 10th,
           which the model has never seen. Tests generalisation to traffic
           from a new place.
  shuffle  train on randomly shuffled labels. The model can then only
           memorise; on the real test labels it should do no better than
           always guessing "attack" (balanced accuracy ~50%). A high score
           here would mean leakage.
  curve    learning curve: train on 0.1%, 1%, 10%, 50% of the training set
           and test on the same test set. Shows how easy the task is.

Note: features use the scaler fitted on the 70% training part; cv and loro
reuse those scaled values (min-max ranges only, no labels involved).

Each check saves results/split_701515/overfitting_checks/<check>.json;
src/show_results.py prints them.

Run: venv\\Scripts\\python.exe src\\overfitting_checks.py [cv] [loro] [shuffle] [curve]
     (no arguments = all four; loro also accepts router numbers, e.g. "loro 1 2 3")
"""

import json
import os
import sys
import time

import numpy as np
import tensorflow as tf
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.utils.class_weight import compute_class_weight

from model import build_model, tune_threshold

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "processed_701515")
OUT_DIR = os.path.join(PROJECT_ROOT, "results", "split_701515", "overfitting_checks")
SEED = 42
CHECKS = ("cv", "loro", "shuffle", "curve")


def load_parts():
    d = {}
    for s in ("train", "val", "test"):
        d[s] = (np.load(os.path.join(DATA_DIR, f"X_{s}.npy")),
                np.load(os.path.join(DATA_DIR, f"y_{s}.npy")),
                np.load(os.path.join(DATA_DIR, f"{s}_client.npy")))
    return d


def seed_all(seed):
    np.random.seed(seed)
    tf.random.set_seed(seed)


def fit(X, y, seed=SEED, X_val=None, y_val=None):
    """Train the project MLP like the centralized model. If no validation set
    is given, 10% of (X, y) is held out for early stopping and the threshold."""
    seed_all(seed)
    if X_val is None:
        X, X_val, y, y_val = train_test_split(X, y, test_size=0.1, stratify=y,
                                              random_state=seed)
    w = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
    model = build_model(X.shape[1])
    hist = model.fit(X, y, epochs=80, batch_size=256, validation_data=(X_val, y_val),
                     class_weight={0: w[0], 1: w[1]}, verbose=0,
                     callbacks=[tf.keras.callbacks.EarlyStopping(
                         monitor="val_loss", patience=10, restore_best_weights=True)])
    return model, tune_threshold(model, X_val, y_val), len(hist.history["loss"]), X, y


def scores(model, threshold, X, y):
    pred = (model.predict(X, verbose=0, batch_size=4096).ravel() >= threshold).astype(int)
    return {"accuracy": float(accuracy_score(y, pred)),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
            "f1": float(f1_score(y, pred, zero_division=0)),
            "errors": int((pred != y).sum()), "flows": int(len(y))}


def save(name, obj):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{name}.json"), "w") as f:
        json.dump(obj, f, indent=2)


def check_cv(d):
    X = np.concatenate([d[s][0] for s in d])
    y = np.concatenate([d[s][1] for s in d])
    client = np.concatenate([d[s][2] for s in d])
    folds = []
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    for k, (tr, te) in enumerate(skf.split(X, client * 2 + y), start=1):
        t0 = time.time()
        model, thr, epochs, X_fit, y_fit = fit(X[tr], y[tr], seed=SEED + k)
        f = {"fold": k, "epochs": epochs, "threshold": thr,
             "train": scores(model, thr, X_fit, y_fit), "test": scores(model, thr, X[te], y[te]),
             "minutes": round((time.time() - t0) / 60, 1)}
        folds.append(f)
        print(f"  cv fold {k}: train acc {f['train']['accuracy']:.4f}  "
              f"test acc {f['test']['accuracy']:.4f}  ({f['test']['errors']} errors in "
              f"{f['test']['flows']})  {f['minutes']} min", flush=True)
        save("cv", {"folds": folds})
    tr_acc = [f["train"]["accuracy"] for f in folds]
    te_acc = [f["test"]["accuracy"] for f in folds]
    save("cv", {"folds": folds, "train_accuracy_mean": float(np.mean(tr_acc)),
                "test_accuracy_mean": float(np.mean(te_acc)),
                "test_accuracy_std": float(np.std(te_acc))})


def check_loro(d, routers):
    X = np.concatenate([d[s][0] for s in d])
    y = np.concatenate([d[s][1] for s in d])
    client = np.concatenate([d[s][2] for s in d])
    path = os.path.join(OUT_DIR, "loro.json")
    out = {}
    if os.path.exists(path):
        with open(path) as f:
            out = json.load(f)
    for r in routers:
        t0 = time.time()
        held = client == r - 1
        model, thr, epochs, X_fit, y_fit = fit(X[~held], y[~held], seed=SEED + r)
        res = {"router": r, "epochs": epochs, "threshold": thr,
               "attack_share": float(y[held].mean()),
               "train": scores(model, thr, X_fit, y_fit), "unseen_router": scores(model, thr, X[held], y[held]),
               "minutes": round((time.time() - t0) / 60, 1)}
        print(f"  router {r:2d} left out: train acc {res['train']['accuracy']:.4f}  "
              f"unseen router acc {res['unseen_router']['accuracy']:.4f}  balanced "
              f"{res['unseen_router']['balanced_accuracy']:.4f}  {res['minutes']} min", flush=True)
        # re-read before writing: several processes may fill this file
        if os.path.exists(path):
            with open(path) as f:
                out = json.load(f)
        out[str(r)] = res
        save("loro", out)


def check_shuffle(d):
    X, y, _ = d["train"]
    Xv, yv, _ = d["val"]
    Xt, yt, _ = d["test"]
    rng = np.random.default_rng(SEED)
    model, thr, epochs, _, _ = fit(X, rng.permutation(y), X_val=Xv, y_val=rng.permutation(yv))
    res = {"epochs": epochs, "threshold": thr,
           "test_with_real_labels": scores(model, thr, Xt, yt),
           "always_attack_accuracy": float(yt.mean())}
    print(f"  shuffled labels: test acc {res['test_with_real_labels']['accuracy']:.4f} "
          f"(always-attack baseline {res['always_attack_accuracy']:.4f}), balanced acc "
          f"{res['test_with_real_labels']['balanced_accuracy']:.4f}", flush=True)
    save("shuffle", res)


def check_curve(d):
    X, y, _ = d["train"]
    Xv, yv, _ = d["val"]
    Xt, yt, _ = d["test"]
    points = []
    for frac in (0.001, 0.01, 0.1, 0.5):
        idx, _ = train_test_split(np.arange(len(y)), train_size=frac, stratify=y,
                                  random_state=SEED)
        model, thr, epochs, _, _ = fit(X[idx], y[idx], X_val=Xv, y_val=yv)
        p = {"fraction": frac, "train_flows": int(len(idx)), "epochs": epochs,
             "train": scores(model, thr, X[idx], y[idx]), "test": scores(model, thr, Xt, yt)}
        points.append(p)
        print(f"  {100 * frac:5.1f}% of train ({len(idx):6d} flows): train acc "
              f"{p['train']['accuracy']:.4f}  test acc {p['test']['accuracy']:.4f}", flush=True)
        save("curve", {"points": points})


def main():
    args = sys.argv[1:]
    checks = [a for a in args if a in CHECKS] or list(CHECKS)
    routers = [int(a) for a in args if a.isdigit()] or list(range(1, 11))
    d = load_parts()
    for c in checks:
        print(f"\n=== {c} ===", flush=True)
        if c == "cv":
            check_cv(d)
        elif c == "loro":
            check_loro(d, routers)
        elif c == "shuffle":
            check_shuffle(d)
        else:
            check_curve(d)


if __name__ == "__main__":
    main()
