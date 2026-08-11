"""
Phase 4 — Client simulation (data partitioning).

Splits the preprocessed NSL-KDD training data across multiple simulated
"clients" two different ways:

  - IID split: random, even split — every client sees a similar mix of
    traffic. Used to get the federated pipeline working first.
  - Non-IID split: a Dirichlet-based partition over the original attack-type
    categories (not just the binary label), so different clients end up
    with genuinely different traffic profiles — e.g. one client dominated
    by "neptune" attacks, another mostly "normal" traffic. This is the
    split the project's actual research question depends on (see README,
    "Research Question").

Both splits are saved as arrays of per-sample client-ID assignments in
data/processed/, so later phases (model training) just load them instead of
recomputing.

Run: venv\\Scripts\\python.exe src\\client_simulation.py
"""

import os

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")

DEFAULT_NUM_CLIENTS = 5
DEFAULT_ALPHA = 0.5  # Dirichlet concentration: smaller = more non-IID
DEFAULT_SEED = 42


def load_processed_data():
    X_train = np.load(os.path.join(PROCESSED_DIR, "X_train.npy"))
    y_train = np.load(os.path.join(PROCESSED_DIR, "y_train.npy"))
    attack_type = pd.read_csv(
        os.path.join(PROCESSED_DIR, "train_attack_type.csv")
    )["attack_type"].to_numpy()
    return X_train, y_train, attack_type


def split_iid(num_samples: int, num_clients: int, seed: int = DEFAULT_SEED) -> np.ndarray:
    """Return an array of length num_samples giving each sample's client ID,
    assigned by a random, even shuffle-and-split."""
    rng = np.random.default_rng(seed)
    indices = rng.permutation(num_samples)
    chunks = np.array_split(indices, num_clients)

    assignment = np.empty(num_samples, dtype=int)
    for client_id, chunk in enumerate(chunks):
        assignment[chunk] = client_id
    return assignment


def split_non_iid_dirichlet(
    labels: np.ndarray,
    num_clients: int,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
) -> np.ndarray:
    """Return an array of length len(labels) giving each sample's client ID,
    assigned via a Dirichlet-distributed partition over `labels`' categories
    (the standard approach for simulating non-IID FL clients, e.g. Hsu et
    al. 2019). Smaller `alpha` -> more skewed / non-IID clients."""
    rng = np.random.default_rng(seed)
    num_samples = len(labels)
    assignment = np.full(num_samples, -1, dtype=int)

    for category in np.unique(labels):
        category_indices = np.where(labels == category)[0]
        rng.shuffle(category_indices)

        proportions = rng.dirichlet(alpha * np.ones(num_clients))
        split_sizes = (proportions * len(category_indices)).astype(int)
        # Give any leftover samples (from integer rounding) to the last client.
        split_sizes[-1] += len(category_indices) - split_sizes.sum()

        start = 0
        for client_id, size in enumerate(split_sizes):
            assignment[category_indices[start:start + size]] = client_id
            start += size

    assert (assignment >= 0).all(), "every sample must be assigned to a client"
    return assignment


def summarize(assignment: np.ndarray, y: np.ndarray, attack_type: np.ndarray, num_clients: int, title: str):
    print(f"\n--- {title} ---")
    for client_id in range(num_clients):
        mask = assignment == client_id
        n = mask.sum()
        attack_pct = 100 * y[mask].mean() if n > 0 else 0.0
        top_types = pd.Series(attack_type[mask]).value_counts().head(3)
        top_types_str = ", ".join(f"{t}={c}" for t, c in top_types.items())
        print(f"  Client {client_id}: {n} samples, {attack_pct:.1f}% attack "
              f"| top categories: {top_types_str}")


def main():
    X_train, y_train, attack_type = load_processed_data()
    num_samples = len(y_train)
    print(f"Loaded {num_samples} training samples.")

    iid_assignment = split_iid(num_samples, DEFAULT_NUM_CLIENTS)
    summarize(iid_assignment, y_train, attack_type, DEFAULT_NUM_CLIENTS, "IID split")

    non_iid_assignment = split_non_iid_dirichlet(
        attack_type, DEFAULT_NUM_CLIENTS, alpha=DEFAULT_ALPHA
    )
    summarize(non_iid_assignment, y_train, attack_type, DEFAULT_NUM_CLIENTS,
              f"Non-IID split (Dirichlet, alpha={DEFAULT_ALPHA})")

    np.save(os.path.join(PROCESSED_DIR, "client_assignment_iid.npy"), iid_assignment)
    np.save(os.path.join(PROCESSED_DIR, "client_assignment_non_iid.npy"), non_iid_assignment)
    print(f"\nSaved client assignments to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
