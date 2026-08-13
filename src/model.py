"""
Phase 5 — Model definition, plus a centralized (non-federated) baseline run.

Defines the MLP architecture used throughout the project (see README,
"Model" section): a plain feedforward network sized for the 122-feature
preprocessed NSL-KDD data, doing binary (normal vs attack) classification.

Running this file also trains the model the normal, non-federated way (on
the full training set at once) and evaluates it on the held-out test set.
This produces the **centralized baseline** — the number every later
federated result (Phase 6 onward) gets compared against, to answer "how
close does federated training get to normal, non-private training?"

Run: venv\\Scripts\\python.exe src\\model.py
"""

import json
import os

import numpy as np
import tensorflow as tf
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                              precision_score, recall_score)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")


def build_model(input_dim: int) -> tf.keras.Model:
    """The project's MLP architecture (README > Model):
    input -> Dense(128, relu) -> Dense(64, relu) -> Dense(1, sigmoid)."""
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(input_dim,)),
        tf.keras.layers.Dense(128, activation="relu"),
        tf.keras.layers.Dense(64, activation="relu"),
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


def evaluate(model: tf.keras.Model, X_test: np.ndarray, y_test: np.ndarray) -> dict:
    y_prob = model.predict(X_test, verbose=0).ravel()
    y_pred = (y_prob >= 0.5).astype(int)

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred)),
        "recall": float(recall_score(y_test, y_pred)),
        "f1_score": float(f1_score(y_test, y_pred)),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
    }
    return metrics


def run_centralized_baseline(epochs: int = 15, batch_size: int = 256):
    X_train, y_train, X_test, y_test = load_processed_data()
    print(f"Training centralized baseline on {X_train.shape[0]} samples, "
          f"{X_train.shape[1]} features, for {epochs} epochs...")

    model = build_model(input_dim=X_train.shape[1])
    model.fit(
        X_train, y_train,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=0.1,
        verbose=2,
    )

    print("\nEvaluating on held-out test set...")
    metrics = evaluate(model, X_test, y_test)

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
