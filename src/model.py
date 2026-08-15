"""
Phase 5 — Model definition, plus a centralized (non-federated) baseline run.

Defines the MLP architecture used throughout the project (see README,
"Model" section): a plain feedforward network sized for the 122-feature
preprocessed NSL-KDD data, doing binary (normal vs attack) classification.
Includes Dropout regularization, a proper stratified train/validation split
(not Keras's default trailing-slice validation_split, which is unsafe on
unshuffled data), early stopping, class weighting, and decision-threshold
tuning (fit on the validation split only, never on the test set).

Running this file also trains the model the normal, non-federated way (on
the full training set at once) and evaluates it on the held-out test set.
This produces the **centralized baseline** — the number every later
federated result (Phase 6 onward) gets compared against, to answer "how
close does federated training get to normal, non-private training?"

Run: venv\\Scripts\\python.exe src\\model.py
"""

import json
import os
import random

import numpy as np
import tensorflow as tf
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                              precision_score, recall_score)
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

# Full determinism setup -- tf.random.set_seed() ALONE is not enough: Keras's
# per-epoch data shuffling draws from NumPy/Python's random state, not
# TensorFlow's, so without also seeding those, accuracy still drifts run to
# run (observed: 80.6% vs 83.7% between two "identical" runs). Also forcing
# single-threaded ops, since CPU op parallelism itself is a separate source
# of float non-determinism independent of any seed.
SEED = 42
os.environ["PYTHONHASHSEED"] = str(SEED)
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)
tf.config.threading.set_intra_op_parallelism_threads(1)
tf.config.threading.set_inter_op_parallelism_threads(1)


def build_model(input_dim: int) -> tf.keras.Model:
    """The project's MLP architecture (README > Model):
    input -> Dense(256) -> Dropout -> Dense(128) -> Dropout ->
    Dense(64) -> Dropout -> Dense(1, sigmoid), with light L2 weight decay
    on every Dense layer. Sized up from the original 128/64 version, with
    added L2 regularization, to give the model more raw capacity while
    still controlling overfitting -- an attempt to close as much of the
    official-split generalization gap as legitimately possible (see
    README > Phase 5 for why this gap has a hard floor NSL-KDD is
    specifically designed to expose, not just a tuning problem)."""
    l2 = tf.keras.regularizers.l2(1e-4)
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(input_dim,)),
        tf.keras.layers.Dense(256, activation="relu", kernel_regularizer=l2),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(128, activation="relu", kernel_regularizer=l2),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(64, activation="relu", kernel_regularizer=l2),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(
        optimizer="adam",
        loss="binary_crossentropy",
        metrics=["accuracy"],
    )
    return model


def load_processed_data():
    X_train = np.load(os.path.join(PROCESSED_DIR, "X_train.npy"))
    y_train = np.load(os.path.join(PROCESSED_DIR, "y_train.npy"))
    X_test = np.load(os.path.join(PROCESSED_DIR, "X_test.npy"))
    y_test = np.load(os.path.join(PROCESSED_DIR, "y_test.npy"))
    return X_train, y_train, X_test, y_test


def evaluate(model: tf.keras.Model, X_test: np.ndarray, y_test: np.ndarray,
             threshold: float = 0.5) -> dict:
    y_prob = model.predict(X_test, verbose=0).ravel()
    y_pred = (y_prob >= threshold).astype(int)

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred)),
        "recall": float(recall_score(y_test, y_pred)),
        "f1_score": float(f1_score(y_test, y_pred)),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "threshold": threshold,
    }
    return metrics


def tune_threshold(model: tf.keras.Model, X_val: np.ndarray, y_val: np.ndarray) -> float:
    """Sweep decision thresholds on the VALIDATION set only (never the test
    set) and return the one that maximizes accuracy. Default 0.5 is not
    necessarily optimal, especially when precision/recall are imbalanced."""
    y_prob = model.predict(X_val, verbose=0).ravel()
    best_threshold, best_accuracy = 0.5, 0.0
    for threshold in np.arange(0.1, 0.91, 0.02):
        y_pred = (y_prob >= threshold).astype(int)
        acc = accuracy_score(y_val, y_pred)
        if acc > best_accuracy:
            best_accuracy, best_threshold = acc, threshold
    return round(float(best_threshold), 2)


def run_centralized_baseline(epochs: int = 80, batch_size: int = 256):
    X_train_full, y_train_full, X_test, y_test = load_processed_data()

    # Proper stratified shuffle split -- Keras's validation_split just
    # slices the tail of the (unshuffled) array, which is not a safe
    # validation set here.
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full, y_train_full, test_size=0.1, stratify=y_train_full,
        random_state=42,
    )

    class_weights = compute_class_weight(
        class_weight="balanced", classes=np.array([0, 1]), y=y_train
    )
    class_weight_dict = {0: class_weights[0], 1: class_weights[1]}

    print(f"Training centralized baseline on {X_train.shape[0]} samples "
          f"({X_val.shape[0]} held out for validation), "
          f"{X_train.shape[1]} features, up to {epochs} epochs "
          f"(early stopping enabled)...")

    model = build_model(input_dim=X_train.shape[1])
    early_stopping = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=10, restore_best_weights=True,
    )
    model.fit(
        X_train, y_train,
        epochs=epochs,
        batch_size=batch_size,
        validation_data=(X_val, y_val),
        class_weight=class_weight_dict,
        callbacks=[early_stopping],
        verbose=2,
    )

    threshold = tune_threshold(model, X_val, y_val)
    print(f"\nTuned decision threshold (on validation set): {threshold}")

    print("Evaluating on held-out test set...")
    metrics = evaluate(model, X_test, y_test, threshold=threshold)

    print(f"  Accuracy:  {metrics['accuracy']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")
    print(f"  F1-score:  {metrics['f1_score']:.4f}")
    print(f"  Confusion matrix: {metrics['confusion_matrix']}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "centralized_baseline.json")
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved centralized baseline metrics to {out_path}")

    return metrics


if __name__ == "__main__":
    run_centralized_baseline()
