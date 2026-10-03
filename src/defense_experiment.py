"""
Phase 9 — Improved defenses, a backdoor attack, and NSL-KDD replication.

Builds on Phase 8 (src/protocol_experiment.py), whose results showed two
weaknesses: (1) the defense failed when a large client (FLNET2023 router
10, 25% of the data) attacked, and (2) flagged updates were simply
dropped. This experiment adds the fixes and widens the evaluation:

Policies (same seed => same attackers, same model init):
  - none:         plain FedAvg, no protocol
  - v1:           Phase 8 protocol — global thresholds, flagged updates
                  dropped, plain sample-count weights
  - v2:           v1 + capped FedAvg weights (no client above 1.5x an equal
                  share) + second check (flagged updates re-tested against
                  a trimmed-mean reference and rescued if close enough)
  - v2_mondrian:  v2 with Mondrian per-cluster thresholds

Attacks (NUM_ATTACKERS of 10 clients, starting after calibration):
  - label_flip:   attackers train on 1 - y
  - backdoor:     attackers add flows of one target attack type, labelled
                  "normal", to their local data (an attacker can generate
                  its own attack traffic). Goal: the global model lets that
                  attack type through while staying accurate on everything
                  else — much quieter than label flipping. Measured by the
                  attack success rate (ASR): share of test flows of the
                  target type classified as normal.

Datasets:
  - flnet:   FLNET2023, real per-router clients (data/processed/)
  - nslkdd:  NSL-KDD, simulated Dirichlet non-IID clients
             (data/processed_nslkdd/, from src/preprocess_nslkdd.py)

Results are written to results/defense_experiment.json after every run, and
runs already in that file are skipped, so the experiment can be stopped and
resumed.

Run: venv\\Scripts\\python.exe src\\defense_experiment.py
"""

import json
import os
import random
import sys
import time

import numpy as np
import pandas as pd
import tensorflow as tf
from scipy import stats

from model import build_model
from protocol import (AnomalyScorer, Fingerprinter, GlobalCalibrator,
                      MondrianCalibrator, capped_weights, flatten, is_flagged,
                      pack, second_check, unflatten, unpack)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_PATH = os.path.join(PROJECT_ROOT, "results", "defense_experiment.json")

DATASETS = {
    "flnet": {"dir": os.path.join(PROJECT_ROOT, "data", "processed"),
              "assignment": "client_assignment_router.npy",
              "backdoor_target": "DoS-slowhttp"},
    "nslkdd": {"dir": os.path.join(PROJECT_ROOT, "data", "processed_nslkdd"),
               "assignment": "client_assignment_noniid.npy",
               "backdoor_target": "satan"},
}
ATTACKS = ("label_flip", "backdoor")
POLICIES = ("none", "v1", "v2", "v2_mondrian")

# FLNET2023 runs are ~4x slower (564k vs 126k training rows), so fewer seeds.
SEEDS_PER_DATASET = {"nslkdd": 10, "flnet": 5}
NUM_ROUNDS = 12
CALIBRATION_ROUNDS = 5
NUM_ATTACKERS = 2
LOCAL_EPOCHS = 1
BATCH_SIZE = 256
ALPHA = 0.05
NUM_CLUSTERS = 3
WEIGHT_CAP_FACTOR = 1.5      # max weight = 1.5 x equal share (15% of 10)
TRIM_FRACTION = 0.2          # trimmed-mean reference for the second check
BACKDOOR_RATIO = 0.5         # poisoned rows added = 50% of attacker's data


def seed_everything(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def load_dataset(name: str) -> dict:
    cfg = DATASETS[name]
    d = cfg["dir"]
    data = {
        "X": np.load(os.path.join(d, "X_train.npy")),
        "y": np.load(os.path.join(d, "y_train.npy")),
        "X_test": np.load(os.path.join(d, "X_test.npy")),
        "y_test": np.load(os.path.join(d, "y_test.npy")),
        "assignment": np.load(os.path.join(d, cfg["assignment"])),
        "train_type": pd.read_csv(os.path.join(d, "train_attack_type.csv"))["attack_type"].to_numpy(),
        "test_type": pd.read_csv(os.path.join(d, "test_attack_type.csv"))["attack_type"].to_numpy(),
    }
    target = cfg["backdoor_target"]
    data["target"] = target
    data["target_train_idx"] = np.where(data["train_type"] == target)[0]
    data["target_test_mask"] = data["test_type"] == target
    shapes = [w.shape for w in build_model(data["X"].shape[1]).get_weights()]
    data["fingerprinter"] = Fingerprinter(shapes)
    return data


def local_data(c: int, attack: str, attacking: bool, is_attacker: bool,
               data: dict, rng: np.random.Generator):
    mask = data["assignment"] == c
    X_c, y_c = data["X"][mask], data["y"][mask]
    if not (attacking and is_attacker):
        return X_c, y_c
    if attack == "label_flip":
        return X_c, 1 - y_c
    # backdoor: target-type flows relabelled as normal
    n = min(len(data["target_train_idx"]), int(BACKDOOR_RATIO * len(y_c)))
    idx = rng.choice(data["target_train_idx"], size=n, replace=False)
    X_p = np.concatenate([X_c, data["X"][idx]])
    y_p = np.concatenate([y_c, np.zeros(n, dtype=y_c.dtype)])
    order = rng.permutation(len(y_p))
    return X_p[order], y_p[order]


def evaluate(model, data: dict) -> dict:
    prob = model.predict(data["X_test"], verbose=0, batch_size=4096).ravel()
    pred = (prob >= 0.5).astype(int)
    target = data["target_test_mask"]
    return {
        "accuracy": float((pred == data["y_test"]).mean()),
        "clean_accuracy": float((pred[~target] == data["y_test"][~target]).mean()),
        "backdoor_asr": float((pred[target] == 0).mean()),
    }


def run_once(dataset: str, attack: str, policy: str, seed: int, attackers: set,
             data: dict) -> dict:
    X = data["X"]
    num_clients = int(data["assignment"].max()) + 1
    seed_everything(seed)
    rng = np.random.default_rng(seed)

    global_model = build_model(X.shape[1])
    local_model = build_model(X.shape[1])
    like = global_model.get_weights()
    global_vec = flatten(like)

    fingerprinter = data["fingerprinter"]
    keys = {c: rng.bytes(32) for c in range(num_clients)}
    scorer = AnomalyScorer()
    calibrator = (None if policy == "none"
                  else MondrianCalibrator(ALPHA, NUM_CLUSTERS, seed) if policy == "v2_mondrian"
                  else GlobalCalibrator(ALPHA))
    improved = policy in ("v2", "v2_mondrian")

    decisions = []   # (round, client, malicious, flagged, rescued)
    history = []

    for round_num in range(1, NUM_ROUNDS + 1):
        attacking = round_num > CALIBRATION_ROUNDS
        deltas, counts = {}, {}
        fingerprints = {}
        for c in range(num_clients):
            X_c, y_c = local_data(c, attack, attacking, c in attackers, data, rng)
            local_model.set_weights(unflatten(global_vec, like))
            local_model.fit(X_c, y_c, epochs=LOCAL_EPOCHS, batch_size=BATCH_SIZE, verbose=0)
            delta = flatten(local_model.get_weights()) - global_vec
            n = int((data["assignment"] == c).sum())
            if policy == "none":
                deltas[c], counts[c] = delta, n
                continue
            header, verified, reason = unpack(
                pack(c, round_num, n, delta, keys[c], fingerprinter), keys, fingerprinter)
            assert reason is None, reason
            deltas[c], counts[c], fingerprints[c] = verified, header["n"], header["fp"]

        accepted = deltas
        if policy != "none":
            scores = scorer.score_round(fingerprints)
            if not attacking:
                for c in fingerprints:
                    calibrator.add(c, scores[c], fingerprints[c])
                if round_num == CALIBRATION_ROUNDS:
                    calibrator.fit()
            else:
                passed = {c: d for c, d in deltas.items()
                          if not is_flagged(scores[c], calibrator.threshold_for(c))}
                flagged = {c: d for c, d in deltas.items() if c not in passed}
                rescued = second_check(passed, flagged, TRIM_FRACTION) if improved else {}
                accepted = {**passed, **rescued}
                for c in deltas:
                    decisions.append((round_num, c, c in attackers, c in flagged, c in rescued))
            scorer.remember(fingerprints)
        elif attacking:
            decisions += [(round_num, c, c in attackers, False, False) for c in deltas]

        if accepted:
            sub = {c: counts[c] for c in accepted}
            if improved:
                weights = capped_weights(sub, WEIGHT_CAP_FACTOR)
            else:
                total = sum(sub.values())
                weights = {c: n / total for c, n in sub.items()}
            global_vec = global_vec + sum(accepted[c] * weights[c] for c in accepted)
        global_model.set_weights(unflatten(global_vec, like))
        history.append(evaluate(global_model, data))

    mal = [d for d in decisions if d[2]]
    hon = [d for d in decisions if not d[2]]
    mean = lambda rows, i: float(np.mean([r[i] for r in rows])) if rows else None
    return {
        "dataset": dataset, "attack": attack, "policy": policy, "seed": seed,
        "attackers": sorted(int(a) for a in attackers),
        "final": history[-1],
        "by_round": history,
        # "caught" = excluded from aggregation (flagged and not rescued)
        "detection_rate": mean([(0, 0, 0, d[3] and not d[4]) for d in mal], 3),
        "false_positive_rate": mean([(0, 0, 0, d[3] and not d[4]) for d in hon], 3),
        "flagged_rate_malicious": mean(mal, 3),
        "flagged_rate_honest": mean(hon, 3),
        "rescued_honest": int(sum(d[4] for d in hon)),
        "rescued_malicious": int(sum(d[4] for d in mal)),
    }


def summarize(runs: list) -> dict:
    out = {}
    for dataset in DATASETS:
        for attack in ATTACKS:
            group = [r for r in runs if r["dataset"] == dataset and r["attack"] == attack]
            if not group:
                continue
            entry = {}
            for policy in POLICIES:
                rs = [r for r in group if r["policy"] == policy]
                if not rs:
                    continue
                e = {"runs": len(rs)}
                for key in ("accuracy", "clean_accuracy", "backdoor_asr"):
                    vals = [r["final"][key] for r in rs]
                    e[f"{key}_mean"], e[f"{key}_std"] = float(np.mean(vals)), float(np.std(vals))
                if policy != "none":
                    for key in ("detection_rate", "false_positive_rate"):
                        vals = [r[key] for r in rs]
                        e[f"{key}_mean"], e[f"{key}_std"] = float(np.mean(vals)), float(np.std(vals))
                    e["rescued_honest"] = sum(r["rescued_honest"] for r in rs)
                    e["rescued_malicious"] = sum(r["rescued_malicious"] for r in rs)
                entry[policy] = e
            entry["paired_tests"] = paired_tests(group, attack)
            out[f"{dataset}/{attack}"] = entry
    return out


def paired_tests(group: list, attack: str) -> dict:
    def series(policy, getter):
        rs = sorted((r for r in group if r["policy"] == policy), key=lambda r: r["seed"])
        return {r["seed"]: getter(r) for r in rs}

    def test(a_policy, b_policy, getter):
        a, b = series(a_policy, getter), series(b_policy, getter)
        seeds = sorted(set(a) & set(b))
        if len(seeds) < 2:
            return None
        x = np.array([a[s] for s in seeds])
        y = np.array([b[s] for s in seeds])
        res = {"n": len(seeds), "mean_difference": float(np.mean(x - y))}
        if np.allclose(x, y):
            res.update(t=None, p_value=None)
        else:
            t, p = stats.ttest_rel(x, y)
            res.update(t=float(t), p_value=float(p))
        return res

    main_metric = (lambda r: r["final"]["backdoor_asr"]) if attack == "backdoor" \
        else (lambda r: r["final"]["accuracy"])
    name = "backdoor_asr" if attack == "backdoor" else "accuracy"
    return {
        f"v2_minus_v1_{name}": test("v2", "v1", main_metric),
        f"v1_minus_none_{name}": test("v1", "none", main_metric),
        "v2_minus_v2_mondrian_detection": test("v2", "v2_mondrian", lambda r: r["detection_rate"]),
        "v2_minus_v2_mondrian_fpr": test("v2", "v2_mondrian", lambda r: r["false_positive_rate"]),
    }


def save(runs: list):
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    config = {"seeds_per_dataset": SEEDS_PER_DATASET, "num_rounds": NUM_ROUNDS,
              "calibration_rounds": CALIBRATION_ROUNDS, "num_attackers": NUM_ATTACKERS,
              "local_epochs": LOCAL_EPOCHS, "alpha": ALPHA, "num_clusters": NUM_CLUSTERS,
              "weight_cap_factor": WEIGHT_CAP_FACTOR, "trim_fraction": TRIM_FRACTION,
              "backdoor_ratio": BACKDOOR_RATIO,
              "backdoor_targets": {k: v["backdoor_target"] for k, v in DATASETS.items()}}
    tmp = RESULTS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"config": config, "summary": summarize(runs), "runs": runs}, f, indent=2)
    os.replace(tmp, RESULTS_PATH)


def main():
    datasets = sys.argv[1:] or list(DATASETS)
    runs = []
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            runs = json.load(f)["runs"]
        print(f"Resuming: {len(runs)} runs already done.")
    done = {(r["dataset"], r["attack"], r["policy"], r["seed"]) for r in runs}

    started = time.time()
    # NSL-KDD first: it is ~4x faster, so its results arrive early.
    for dataset in sorted(datasets, key=lambda d: d != "nslkdd"):
        data = load_dataset(dataset)
        num_clients = int(data["assignment"].max()) + 1
        print(f"\n=== {dataset}: {len(data['y'])} train rows, {num_clients} clients, "
              f"backdoor target '{data['target']}' "
              f"({len(data['target_train_idx'])} train / {int(data['target_test_mask'].sum())} test rows)")
        for attack in ATTACKS:
            for seed in range(SEEDS_PER_DATASET[dataset]):
                attackers = set(np.random.default_rng(1000 + seed).choice(
                    num_clients, size=NUM_ATTACKERS, replace=False).tolist())
                for policy in POLICIES:
                    if (dataset, attack, policy, seed) in done:
                        continue
                    r = run_once(dataset, attack, policy, seed, attackers, data)
                    runs.append(r)
                    save(runs)
                    f = r["final"]
                    extra = ("" if policy == "none" else
                             f" caught {r['detection_rate']:.2f} FPR {r['false_positive_rate']:.3f}"
                             f" rescued h{r['rescued_honest']}/m{r['rescued_malicious']}")
                    print(f"{dataset:6s} {attack:10s} seed {seed} att {sorted(a + 1 for a in attackers)} "
                          f"{policy:11s} acc {f['accuracy']:.4f} ASR {f['backdoor_asr']:.3f}{extra} "
                          f"[{(time.time() - started) / 60:.1f} min]", flush=True)

    print("\n" + json.dumps(summarize(runs), indent=2))
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
