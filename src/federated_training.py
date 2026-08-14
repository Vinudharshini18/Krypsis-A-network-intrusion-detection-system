"""
Phase 6 — Federated training loop (FedAvg).

Ties together Phase 3 (preprocessed data), Phase 4 (client splits), and
Phase 5 (the MLP model): runs the standard federated-averaging loop —

  for each round:
    for each client: train a local copy of the global model on that
      client's data slice only
    aggregate the clients' updated weights into a new global model,
      weighted by each client's sample count (standard FedAvg, see
      README > "doubt" thread: this is NOT the paper's separate
      magnitude-based "WFedAvg")
    evaluate the new global model on the held-out test set

and logs per-round metrics, so accuracy-vs-round can be plotted and
compared against the centralized baseline (Phase 5) and between the IID
and non-IID client splits (Phase 4).

Run: venv\\Scripts\\python.exe src\\federated_training.py
"""

import json
import os

import numpy as np
import tensorflow as tf

from model import build_model, evaluate, load_processed_data

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

NUM_ROUNDS = 15
LOCAL_EPOCHS = 2
BATCH_SIZE = 256


def load_client_assignment(split: str) -> np.ndarray:
    filename = f"client_assignment_{split}.npy"
    return np.load(os.path.join(PROCESSED_DIR, filename))


def federated_average(weight_list: list, sample_counts: list) -> list:
    """Standard (sample-size-weighted) FedAvg: average each layer's weights
    across clients, weighted by how many samples each client trained on."""
    total = sum(sample_counts)
    averaged = []
    for layer_idx in range(len(weight_list[0])):
        layer_sum = sum(
            weight_list[i][layer_idx] * (sample_counts[i] / total)
            for i in range(len(weight_list))
        )
        averaged.append(layer_sum)
    return averaged


def run_federated_training(split: str, num_rounds: int = NUM_ROUNDS):
    assert split in ("iid", "non_iid")

    X_train, y_train, X_test, y_test = load_processed_data()
    assignment = load_client_assignment(split)
    num_clients = assignment.max() + 1

    print(f"\n=== Federated training, {split} split, {num_clients} clients, "
          f"{num_rounds} rounds ===")

    global_model = build_model(input_dim=X_train.shape[1])
    global_weights = global_model.get_weights()

    history = []
    for round_num in range(1, num_rounds + 1):
        local_weights = []
        sample_counts = []

        for client_id in range(num_clients):
            mask = assignment == client_id
            X_client, y_client = X_train[mask], y_train[mask]
            if len(X_client) == 0:
                continue

            local_model = build_model(input_dim=X_train.shape[1])
            local_model.set_weights(global_weights)
            local_model.fit(
                X_client, y_client,
                epochs=LOCAL_EPOCHS,
                batch_size=BATCH_SIZE,
                verbose=0,
            )
            local_weights.append(local_model.get_weights())
            sample_counts.append(len(X_client))

        global_weights = federated_average(local_weights, sample_counts)
        global_model.set_weights(global_weights)

        metrics = evaluate(global_model, X_test, y_test)
        metrics["round"] = round_num
        history.append(metrics)
        print(f"  Round {round_num:2d}/{num_rounds} — "
              f"accuracy: {metrics['accuracy']:.4f}, "
              f"precision: {metrics['precision']:.4f}, "
              f"recall: {metrics['recall']:.4f}, "
              f"f1: {metrics['f1_score']:.4f}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"federated_{split}.json")
    with open(out_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"Saved round-by-round metrics to {out_path}")

    return history


def compare_to_baseline(federated_history: list):
    baseline_path = os.path.join(RESULTS_DIR, "centralized_baseline.json")
    if not os.path.exists(baseline_path):
        print("\n(No centralized baseline found — run src/model.py first "
              "to generate one for comparison.)")
        return

    with open(baseline_path) as f:
        baseline = json.load(f)

    final_federated = federated_history[-1]
    gap = baseline["accuracy"] - final_federated["accuracy"]
    print(f"\nCentralized baseline accuracy: {baseline['accuracy']:.4f}")
    print(f"Final federated accuracy:      {final_federated['accuracy']:.4f}")
    print(f"Accuracy gap (centralized - federated): {gap:+.4f}")


if __name__ == "__main__":
    iid_history = run_federated_training("iid")
    compare_to_baseline(iid_history)

    non_iid_history = run_federated_training("non_iid")
    compare_to_baseline(non_iid_history)
