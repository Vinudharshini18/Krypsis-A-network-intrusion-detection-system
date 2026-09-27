"""
Phase 4 — Client assignment (data partitioning).

Assigns every preprocessed FLNET2023 training row to a federated client, two
different ways:

  - Router split (the real one): each of FLNET2023's 10 data-collection
    routers (D1-D10) is one client, holding exactly the traffic captured at
    that router. Heterogeneity here is *real*, not simulated — routers see
    different attack types in very different amounts (e.g. router 10 is
    dominated by a large TCP-flood capture, router 3 sees SQL injection but
    no DDoS at all). This is the split the project's research question
    depends on (see README, "Research Question").
  - IID split (control): the same rows shuffled and dealt evenly across the
    same number of clients, so every client sees a similar traffic mix.
    Comparing the two isolates the effect of realistic non-IID data.

Both are saved as per-sample client-ID arrays in data/processed/, so later
phases (model training) just load them instead of recomputing.

Run: venv\\Scripts\\python.exe src\\client_simulation.py
"""

import os

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")

DEFAULT_SEED = 42


def load_processed_data():
    y_train = np.load(os.path.join(PROCESSED_DIR, "y_train.npy"))
    router = np.load(os.path.join(PROCESSED_DIR, "train_router.npy"))
    attack_type = pd.read_csv(
        os.path.join(PROCESSED_DIR, "train_attack_type.csv")
    )["attack_type"].to_numpy()
    return y_train, router, attack_type


def split_by_router(router: np.ndarray) -> np.ndarray:
    """Client ID = router index, renumbered to 0..num_routers-1 (router 1 ->
    client 0, ..., router 10 -> client 9)."""
    routers = np.unique(router)
    return np.searchsorted(routers, router)


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


def summarize(assignment: np.ndarray, y: np.ndarray, attack_type: np.ndarray, num_clients: int, title: str):
    print(f"\n--- {title} ---")
    for client_id in range(num_clients):
        mask = assignment == client_id
        n = mask.sum()
        attack_pct = 100 * y[mask].mean() if n > 0 else 0.0
        top_types = pd.Series(attack_type[mask]).value_counts().head(4)
        top_types_str = ", ".join(f"{t}={c}" for t, c in top_types.items())
        print(f"  Client {client_id}: {n} samples, {attack_pct:.1f}% attack "
              f"| top categories: {top_types_str}")


def main():
    y_train, router, attack_type = load_processed_data()
    num_samples = len(y_train)
    print(f"Loaded {num_samples} training samples.")

    router_assignment = split_by_router(router)
    num_clients = router_assignment.max() + 1
    summarize(router_assignment, y_train, attack_type, num_clients,
              f"Router split ({num_clients} routers = {num_clients} clients)")

    iid_assignment = split_iid(num_samples, num_clients)
    summarize(iid_assignment, y_train, attack_type, num_clients, "IID split")

    np.save(os.path.join(PROCESSED_DIR, "client_assignment_router.npy"), router_assignment)
    np.save(os.path.join(PROCESSED_DIR, "client_assignment_iid.npy"), iid_assignment)
    print(f"\nSaved client assignments to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
