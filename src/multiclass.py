"""
Phase 10 — Multi-class detection on FLNET2023.

Binary normal-vs-attack detection is saturated on FLNET2023 (Phase 5:
100%), so it cannot show differences between training setups. This phase
predicts the traffic TYPE instead — Normal plus 10 attack types — which is
harder and makes client heterogeneity matter: most routers never see most
attack types (e.g. only router 1 has DDoS-bot, only router 10 DDoS-tcp), so
a federated model must learn them from other clients' updates.

Same MLP as model.py, with a softmax output over the classes. Runs:
  - centralized baseline (all training data in one place)
  - FedAvg on the real router split and on the IID control split
    (10 clients, NUM_ROUNDS rounds, LOCAL_EPOCHS local epochs)

Reports accuracy, macro-F1 (every class counts equally, so rare web attacks
are not drowned out by the large DDoS/DoS classes), per-class recall and the
confusion matrix, evaluated on the TEST capture. Uses the arrays from
src/preprocess.py and src/client_simulation.py.

Run: venv\\Scripts\\python.exe src\\multiclass.py
"""

import json
import os
import random

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight

from protocol import flatten, unflatten

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
RESULTS_PATH = os.path.join(PROJECT_ROOT, "results", "multiclass.json")

SEED = 42
NUM_ROUNDS = 15
LOCAL_EPOCHS = 2
BATCH_SIZE = 256

os.environ["PYTHONHASHSEED"] = str(SEED)
tf.config.threading.set_intra_op_parallelism_threads(1)
tf.config.threading.set_inter_op_parallelism_threads(1)


def seed_everything():
    random.seed(SEED)
    np.random.seed(SEED)
    tf.random.set_seed(SEED)


def build_multiclass_model(input_dim: int, num_classes: int) -> tf.keras.Model:
    """model.py's MLP with a softmax head instead of a single sigmoid."""
    l2 = tf.keras.regularizers.l2(1e-4)
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(input_dim,)),
        tf.keras.layers.Dense(256, activation="relu", kernel_regularizer=l2),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(128, activation="relu", kernel_regularizer=l2),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(64, activation="relu", kernel_regularizer=l2),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(num_classes, activation="softmax"),
    ])
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy",
                  metrics=["accuracy"])
    return model


def load():
    X = np.load(os.path.join(PROCESSED_DIR, "X_train.npy"))
    X_test = np.load(os.path.join(PROCESSED_DIR, "X_test.npy"))
    train_type = pd.read_csv(os.path.join(PROCESSED_DIR, "train_attack_type.csv"))["attack_type"]
    test_type = pd.read_csv(os.path.join(PROCESSED_DIR, "test_attack_type.csv"))["attack_type"]
    classes = sorted(train_type.unique())
    index = {c: i for i, c in enumerate(classes)}
    unknown = set(test_type.unique()) - set(classes)
    if unknown:
        raise ValueError(f"Test classes not seen in training: {unknown}")
    y = train_type.map(index).to_numpy()
    y_test = test_type.map(index).to_numpy()
    splits = {name: np.load(os.path.join(PROCESSED_DIR, f"client_assignment_{name}.npy"))
              for name in ("router", "iid")}
    return X, y, X_test, y_test, classes, splits


def evaluate(model, X_test, y_test, classes) -> dict:
    pred = model.predict(X_test, verbose=0, batch_size=4096).argmax(axis=1)
    labels = list(range(len(classes)))
    recall = recall_score(y_test, pred, labels=labels, average=None, zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_test, pred)),
        "macro_f1": float(f1_score(y_test, pred, labels=labels, average="macro", zero_division=0)),
        "per_class_recall": {c: float(r) for c, r in zip(classes, recall)},
        "confusion_matrix": confusion_matrix(y_test, pred, labels=labels).tolist(),
    }


def report(name: str, m: dict):
    print(f"\n{name}: accuracy {m['accuracy']:.4f}, macro-F1 {m['macro_f1']:.4f}")
    for c, r in m["per_class_recall"].items():
        print(f"    {c:24s} recall {r:.4f}")


def centralized(X, y, X_test, y_test, classes) -> dict:
    seed_everything()
    X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=0.1, stratify=y,
                                                random_state=SEED)
    weights = compute_class_weight("balanced", classes=np.unique(y_tr), y=y_tr)
    model = build_multiclass_model(X.shape[1], len(classes))
    model.fit(X_tr, y_tr, epochs=60, batch_size=BATCH_SIZE,
              validation_data=(X_val, y_val),
              class_weight=dict(enumerate(weights)),
              callbacks=[tf.keras.callbacks.EarlyStopping(
                  monitor="val_loss", patience=8, restore_best_weights=True)],
              verbose=2)
    return evaluate(model, X_test, y_test, classes)


def federated(X, y, X_test, y_test, classes, assignment) -> dict:
    seed_everything()
    num_clients = int(assignment.max()) + 1
    global_model = build_multiclass_model(X.shape[1], len(classes))
    local_model = build_multiclass_model(X.shape[1], len(classes))
    like = global_model.get_weights()
    global_vec = flatten(like)
    rounds = []
    for round_num in range(1, NUM_ROUNDS + 1):
        deltas, counts = [], []
        for c in range(num_clients):
            mask = assignment == c
            local_model.set_weights(unflatten(global_vec, like))
            local_model.fit(X[mask], y[mask], epochs=LOCAL_EPOCHS,
                            batch_size=BATCH_SIZE, verbose=0)
            deltas.append(flatten(local_model.get_weights()) - global_vec)
            counts.append(int(mask.sum()))
        total = sum(counts)
        global_vec = global_vec + sum(d * (n / total) for d, n in zip(deltas, counts))
        global_model.set_weights(unflatten(global_vec, like))
        m = evaluate(global_model, X_test, y_test, classes)
        rounds.append({"round": round_num, "accuracy": m["accuracy"], "macro_f1": m["macro_f1"]})
        print(f"  round {round_num:2d}: accuracy {m['accuracy']:.4f}, macro-F1 {m['macro_f1']:.4f}",
              flush=True)
    m["by_round"] = rounds
    return m


def main():
    X, y, X_test, y_test, classes, splits = load()
    print(f"{len(classes)} classes: {', '.join(classes)}")
    print("Training classes per router client:")
    for c in range(int(splits['router'].max()) + 1):
        present = sorted(classes[k] for k in np.unique(y[splits['router'] == c]))
        print(f"  router {c + 1}: {', '.join(present)}")

    results = {"classes": classes}
    print("\n=== Centralized ===")
    results["centralized"] = centralized(X, y, X_test, y_test, classes)
    report("Centralized", results["centralized"])
    for split in ("router", "iid"):
        print(f"\n=== FedAvg, {split} split ===")
        results[f"federated_{split}"] = federated(X, y, X_test, y_test, classes, splits[split])
        report(f"FedAvg {split}", results[f"federated_{split}"])

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
