"""
Supplementary diagnostic — NOT a replacement for the official centralized
baseline (src/model.py) or any federated result. Those all correctly use
the official NSL-KDD KDDTrain+/KDDTest+ split, which deliberately includes
attack types in the test set that are absent from training, to benchmark
generalization to unseen attacks rather than memorization.

This script instead pools train+test together and re-splits with a plain
stratified 80/20 split, so every attack type appears in both the training
and evaluation portions. This isolates two different questions:

  - Official split (src/model.py): "how well does the model generalize to
    attack types it has never seen?" -- the harder, more meaningful
    question, and the one used for every real result in this project.
  - This script: "how well does the model learn the attack types it HAS
    seen?" -- shows the model's raw learning capacity, unclamped by the
    unseen-attack generalization gap.

Reporting both, clearly labeled, is more honest than reporting only
whichever number is higher.

Run: venv\\Scripts\\python.exe src\\indistribution_check.py
"""

import json
import os

import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight

from model import build_model, evaluate, tune_threshold

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")


def run_indistribution_check(epochs: int = 50, batch_size: int = 256):
    X_train = np.load(os.path.join(PROCESSED_DIR, "X_train.npy"))
    y_train = np.load(os.path.join(PROCESSED_DIR, "y_train.npy"))
    X_test = np.load(os.path.join(PROCESSED_DIR, "X_test.npy"))
    y_test = np.load(os.path.join(PROCESSED_DIR, "y_test.npy"))

    X_pooled = np.vstack([X_train, X_test])
    y_pooled = np.concatenate([y_train, y_test])

    X_train_new, X_eval, y_train_new, y_eval = train_test_split(
        X_pooled, y_pooled, test_size=0.2, stratify=y_pooled, random_state=42,
    )
    X_train_new, X_val, y_train_new, y_val = train_test_split(
        X_train_new, y_train_new, test_size=0.1, stratify=y_train_new,
        random_state=42,
    )

    class_weights = compute_class_weight(
        class_weight="balanced", classes=np.array([0, 1]), y=y_train_new
    )
    class_weight_dict = {0: class_weights[0], 1: class_weights[1]}

    print(f"[In-distribution diagnostic] Training on {X_train_new.shape[0]} "
          f"samples, evaluating on {X_eval.shape[0]} samples where every "
          f"attack type appears in both...")

    model = build_model(input_dim=X_train_new.shape[1])
    early_stopping = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=6, restore_best_weights=True,
    )
    model.fit(
        X_train_new, y_train_new,
        epochs=epochs,
        batch_size=batch_size,
        validation_data=(X_val, y_val),
        class_weight=class_weight_dict,
        callbacks=[early_stopping],
        verbose=2,
    )

    threshold = tune_threshold(model, X_val, y_val)
    metrics = evaluate(model, X_eval, y_eval, threshold=threshold)

    print(f"\n[In-distribution diagnostic] Results (NOT the official split):")
    print(f"  Accuracy:  {metrics['accuracy']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")
    print(f"  F1-score:  {metrics['f1_score']:.4f}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "indistribution_check.json")
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved to {out_path}")

    return metrics


if __name__ == "__main__":
    run_indistribution_check()
