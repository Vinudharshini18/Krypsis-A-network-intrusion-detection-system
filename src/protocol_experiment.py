"""
Phase 8 — Protocol evaluation: poisoning detection, global vs Mondrian
thresholds (the Research Question), transit tampering, and communication
overhead.

For each random seed, NUM_ATTACKERS of the 10 FLNET2023 router clients are
chosen as malicious. Federated training (router split) runs NUM_ROUNDS
rounds; the first CALIBRATION_ROUNDS are clean and used to calibrate the
protocol's thresholds, after which the malicious clients start a
label-flipping attack (train on 1 - y). The same seed is run under three
policies:

  - none:      plain FedAvg, every update accepted (no protocol)
  - global:    Krypsis protocol, one global threshold per anomaly score
  - mondrian:  Krypsis protocol, per-cluster thresholds

and, in the two protocol runs, one honest message per post-calibration
round has a payload byte flipped in transit, to check the HMAC catches it.

Reported (post-calibration rounds only): attack detection rate, false-
positive rate on honest clients (overall and per router), final test
accuracy, tamper rejections, bytes on the wire vs a generic HTTP/JSON
upload, and pack/verify time. Global vs Mondrian false-positive and
detection rates are compared with a paired t-test across seeds.

Run: venv\\Scripts\\python.exe src\\protocol_experiment.py
"""

import json
import os
import random
import time

import numpy as np
import tensorflow as tf
from scipy import stats

from model import build_model, load_processed_data
from protocol import (AnomalyScorer, Fingerprinter, GlobalCalibrator,
                      MondrianCalibrator, flatten, http_json_size, is_flagged,
                      pack, unflatten, unpack)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

NUM_SEEDS = 15
NUM_ROUNDS = 12
CALIBRATION_ROUNDS = 5
NUM_ATTACKERS = 2
LOCAL_EPOCHS = 1
BATCH_SIZE = 256
ALPHA = 0.05          # per-score conformal level
NUM_CLUSTERS = 3      # Mondrian clusters
POLICIES = ("none", "global", "mondrian")


def seed_everything(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def accuracy(model, X, y) -> float:
    prob = model.predict(X, verbose=0, batch_size=4096).ravel()
    return float(((prob >= 0.5).astype(int) == y).mean())


def run_once(seed: int, policy: str, attackers: set, data: dict) -> dict:
    X, y, X_test, y_test, assignment = (data[k] for k in
                                         ("X", "y", "X_test", "y_test", "assignment"))
    num_clients = int(assignment.max()) + 1
    seed_everything(seed)
    rng = np.random.default_rng(seed)

    global_model = build_model(X.shape[1])
    local_model = build_model(X.shape[1])
    global_vec = flatten(global_model.get_weights())

    fingerprinter = data["fingerprinter"]
    keys = {c: rng.bytes(32) for c in range(num_clients)}
    scorer = AnomalyScorer()
    calibrator = (GlobalCalibrator(ALPHA) if policy == "global"
                  else MondrianCalibrator(ALPHA, NUM_CLUSTERS, seed) if policy == "mondrian"
                  else None)

    decisions = []   # post-calibration: (round, client, malicious, flagged)
    tamper = {"sent": 0, "rejected": 0}
    timing = {"pack_s": 0.0, "verify_s": 0.0, "messages": 0}
    message_bytes = None
    acc_history = []

    for round_num in range(1, NUM_ROUNDS + 1):
        attacking = round_num > CALIBRATION_ROUNDS
        messages = {}
        for c in range(num_clients):
            mask = assignment == c
            labels = y[mask]
            if attacking and c in attackers:
                labels = 1 - labels                      # label flipping
            local_model.set_weights(unflatten(global_vec, global_model.get_weights()))
            local_model.fit(X[mask], labels, epochs=LOCAL_EPOCHS,
                            batch_size=BATCH_SIZE, verbose=0)
            delta = flatten(local_model.get_weights()) - global_vec
            t = time.perf_counter()
            messages[c] = pack(c, round_num, int(mask.sum()), delta, keys[c], fingerprinter)
            timing["pack_s"] += time.perf_counter() - t
        message_bytes = len(messages[0])

        if policy == "none":
            accepted = {c: np.frombuffer(m[4 + int.from_bytes(m[:4], "big"):-32], np.float32)
                        for c, m in messages.items()}
            counts = {c: int((assignment == c).sum()) for c in accepted}
        else:
            if attacking:
                victim = int(rng.choice([c for c in range(num_clients) if c not in attackers]))
                m = bytearray(messages[victim])
                pos = len(m) - 32 - 1 - int(rng.integers(0, 1000))
                m[pos] ^= 0xFF
                messages[victim] = bytes(m)
                tamper["sent"] += 1

            verified, fingerprints, counts = {}, {}, {}
            for c, m in messages.items():
                t = time.perf_counter()
                header, delta, reason = unpack(m, keys, fingerprinter)
                timing["verify_s"] += time.perf_counter() - t
                timing["messages"] += 1
                if reason is not None:
                    if reason == "bad_tag":
                        tamper["rejected"] += 1
                    continue
                verified[c] = delta
                fingerprints[c] = header["fp"]
                counts[c] = header["n"]

            scores = scorer.score_round(fingerprints)
            if not attacking:
                for c in fingerprints:
                    calibrator.add(c, scores[c], fingerprints[c])
                if round_num == CALIBRATION_ROUNDS:
                    calibrator.fit()
                accepted = verified
            else:
                accepted = {}
                for c, delta in verified.items():
                    flagged = is_flagged(scores[c], calibrator.threshold_for(c))
                    decisions.append((round_num, c, c in attackers, flagged))
                    if not flagged:
                        accepted[c] = delta
            scorer.remember(fingerprints)

        if policy == "none" and attacking:
            decisions += [(round_num, c, c in attackers, False) for c in accepted]

        if accepted:
            total = sum(counts[c] for c in accepted)
            global_vec = global_vec + sum(accepted[c] * (counts[c] / total) for c in accepted)
        global_model.set_weights(unflatten(global_vec, global_model.get_weights()))
        acc_history.append(accuracy(global_model, X_test, y_test))

    mal = [d for d in decisions if d[2]]
    hon = [d for d in decisions if not d[2]]
    per_client_fpr = {}
    for c in range(num_clients):
        if c in attackers:
            continue
        rows = [d for d in hon if d[1] == c]
        if rows:
            per_client_fpr[c] = float(np.mean([d[3] for d in rows]))

    result = {
        "seed": seed,
        "policy": policy,
        "attackers": sorted(int(a) for a in attackers),
        "detection_rate": float(np.mean([d[3] for d in mal])) if mal else None,
        "false_positive_rate": float(np.mean([d[3] for d in hon])) if hon else None,
        "per_client_fpr": per_client_fpr,
        "final_accuracy": acc_history[-1],
        "accuracy_by_round": acc_history,
        "tamper": tamper,
        "message_bytes": message_bytes,
        "mean_pack_ms": 1000 * timing["pack_s"] / (NUM_ROUNDS * num_clients),
        "mean_verify_ms": (1000 * timing["verify_s"] / timing["messages"]
                           if timing["messages"] else None),
    }
    if calibrator is not None:
        result["calibration"] = calibrator.describe()
    return result


def summarize(runs: list) -> dict:
    summary = {}
    for policy in POLICIES:
        rs = [r for r in runs if r["policy"] == policy]
        entry = {"final_accuracy_mean": float(np.mean([r["final_accuracy"] for r in rs])),
                 "final_accuracy_std": float(np.std([r["final_accuracy"] for r in rs]))}
        if policy != "none":
            for key in ("detection_rate", "false_positive_rate"):
                vals = [r[key] for r in rs]
                entry[f"{key}_mean"] = float(np.mean(vals))
                entry[f"{key}_std"] = float(np.std(vals))
            entry["tamper_sent"] = sum(r["tamper"]["sent"] for r in rs)
            entry["tamper_rejected"] = sum(r["tamper"]["rejected"] for r in rs)
            per_client = {}
            for r in rs:
                for c, v in r["per_client_fpr"].items():
                    per_client.setdefault(int(c), []).append(v)
            entry["honest_fpr_by_router"] = {f"router_{c + 1}": float(np.mean(v))
                                             for c, v in sorted(per_client.items())}
        summary[policy] = entry

    g = sorted((r for r in runs if r["policy"] == "global"), key=lambda r: r["seed"])
    m = sorted((r for r in runs if r["policy"] == "mondrian"), key=lambda r: r["seed"])
    tests = {}
    for key in ("false_positive_rate", "detection_rate"):
        a = np.array([r[key] for r in g])
        b = np.array([r[key] for r in m])
        if np.allclose(a, b):
            tests[key] = {"mean_difference_global_minus_mondrian": 0.0,
                          "t": None, "p_value": None, "note": "identical in every seed"}
        else:
            t, p = stats.ttest_rel(a, b)
            tests[key] = {"mean_difference_global_minus_mondrian": float(np.mean(a - b)),
                          "t": float(t), "p_value": float(p)}
    summary["paired_t_test_global_vs_mondrian"] = tests
    return summary


def main():
    X, y, X_test, y_test = load_processed_data()
    assignment = np.load(os.path.join(PROCESSED_DIR, "client_assignment_router.npy"))
    shapes = [w.shape for w in build_model(X.shape[1]).get_weights()]
    fingerprinter = Fingerprinter(shapes)
    data = {"X": X, "y": y, "X_test": X_test, "y_test": y_test,
            "assignment": assignment, "fingerprinter": fingerprinter}
    num_clients = int(assignment.max()) + 1

    sample_delta = np.zeros(fingerprinter.dim, dtype=np.float32) + 1e-3
    comm = {
        "parameters": fingerprinter.dim,
        "raw_payload_bytes": fingerprinter.dim * 4,
        "http_json_bytes": http_json_size(np.random.default_rng(0).standard_normal(
            fingerprinter.dim).astype(np.float32) * 1e-3),
    }
    comm["krypsis_message_bytes"] = len(pack(0, 1, 1, sample_delta, b"k" * 32, fingerprinter))
    comm["krypsis_overhead_bytes"] = comm["krypsis_message_bytes"] - comm["raw_payload_bytes"]
    print(f"Communication: raw payload {comm['raw_payload_bytes']} B, Krypsis message "
          f"{comm['krypsis_message_bytes']} B (+{comm['krypsis_overhead_bytes']} B header+tag), "
          f"HTTP/JSON {comm['http_json_bytes']} B")

    runs = []
    started = time.time()
    for i, seed in enumerate(range(NUM_SEEDS)):
        attackers = set(np.random.default_rng(1000 + seed).choice(
            num_clients, size=NUM_ATTACKERS, replace=False).tolist())
        for policy in POLICIES:
            r = run_once(seed, policy, attackers, data)
            runs.append(r)
            extra = ("" if policy == "none" else
                     f", detect {r['detection_rate']:.2f}, FPR {r['false_positive_rate']:.3f}, "
                     f"tamper {r['tamper']['rejected']}/{r['tamper']['sent']}")
            print(f"seed {seed:2d} attackers {sorted(a + 1 for a in attackers)} "
                  f"{policy:8s}: acc {r['final_accuracy']:.4f}{extra} "
                  f"[{(time.time() - started) / 60:.1f} min]", flush=True)

    summary = summarize(runs)
    config = {"num_seeds": NUM_SEEDS, "num_rounds": NUM_ROUNDS,
              "calibration_rounds": CALIBRATION_ROUNDS, "num_attackers": NUM_ATTACKERS,
              "attack": "label flipping", "local_epochs": LOCAL_EPOCHS, "alpha": ALPHA,
              "num_clusters": NUM_CLUSTERS, "split": "router"}
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, "protocol_experiment.json")
    with open(out, "w") as f:
        json.dump({"config": config, "communication": comm, "summary": summary,
                   "runs": runs}, f, indent=2)
    print("\n" + json.dumps(summary, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
