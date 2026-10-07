"""
Phase 11 — Robustness: client dropout, distribution shift, scalability.

The three remaining stretch goals from README > Scope, all on FLNET2023's
router split with the Phase 9 "v2" protocol (global or Mondrian thresholds
+ weight cap + second check):

  dropout:  every round, each client is independently offline with
            probability p (p = 0, 0.2, 0.4); 2 label-flipping attackers.
            Compared with plain FedAvg ("none") at the same p.
            Question: does the protocol still work when the set of clients
            changes from round to round?

  shift:    no attackers. After round SHIFT_ROUND, one honest router
            (router 3 — mostly normal traffic) starts seeing an attack type
            it has never seen (DDoS-stomp, correctly labelled), at
            SHIFT_RATIO of its own data size. Global vs Mondrian thresholds.
            Question: is an honest client whose traffic suddenly changes
            wrongly rejected — and does Mondrian calibration help?

  scale:    each router's data is split at random into k sub-clients
            (k = 1, 2, 4 -> 10, 20, 40 clients), with 20% of clients
            label-flipping. Global vs Mondrian thresholds.
            Question: does Mondrian start to help once each cluster has
            more clients to calibrate on (the explanation offered for its
            null result in Phases 8-9)? And how does server time scale?

Results are written to results/robustness_experiment.json after every run;
runs already there are skipped (resumable).

Run: venv\\Scripts\\python.exe src\\robustness_experiment.py
"""

import json
import os
import time

import numpy as np
from scipy import stats

from defense_experiment import (CALIBRATION_ROUNDS, LOCAL_EPOCHS, BATCH_SIZE, ALPHA,
                                NUM_CLUSTERS, NUM_ROUNDS, TRIM_FRACTION,
                                WEIGHT_CAP_FACTOR, evaluate, load_dataset,
                                seed_everything)
from model import build_model
from protocol import (AnomalyScorer, GlobalCalibrator, MondrianCalibrator,
                      capped_weights, flatten, is_flagged, pack, second_check,
                      unflatten, unpack)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_PATH = os.path.join(PROJECT_ROOT, "results", "robustness_experiment.json")

NUM_SEEDS = 5
ATTACKER_FRACTION = 0.2
DROPOUT_RATES = (0.0, 0.2, 0.4)
SCALE_FACTORS = (1, 2, 4)
SHIFT_ROUND = 8
SHIFT_CLIENT = 2              # router 3 (0-based)
SHIFT_TYPE = "DDoS-stomp"
SHIFT_RATIO = 0.3


def split_clients(assignment: np.ndarray, k: int, seed: int) -> np.ndarray:
    """Split every client's rows at random into k sub-clients (client c ->
    sub-clients c*k .. c*k+k-1), keeping each router's traffic profile."""
    if k == 1:
        return assignment.copy()
    rng = np.random.default_rng(seed)
    out = np.empty_like(assignment)
    for c in np.unique(assignment):
        idx = np.where(assignment == c)[0]
        out[idx] = c * k + rng.integers(0, k, size=len(idx))
    return out


def choose_attackers(num_clients: int, seed: int, exclude=()) -> set:
    candidates = [c for c in range(num_clients) if c not in exclude]
    n = max(1, int(round(ATTACKER_FRACTION * num_clients)))
    return set(np.random.default_rng(1000 + seed).choice(candidates, size=n, replace=False).tolist())


def run_once(data: dict, assignment: np.ndarray, policy: str, seed: int, attackers: set,
             dropout: float = 0.0, shift: bool = False) -> dict:
    X, y = data["X"], data["y"]
    num_clients = int(assignment.max()) + 1
    seed_everything(seed)
    rng = np.random.default_rng(seed)
    drop_rng = np.random.default_rng(10_000 + seed)

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
    shift_idx = np.where(data["train_type"] == SHIFT_TYPE)[0]
    shift_n = int(SHIFT_RATIO * (assignment == SHIFT_CLIENT).sum())
    shift_rows = rng.choice(shift_idx, size=min(shift_n, len(shift_idx)), replace=False)

    decisions = []      # (round, client, malicious, excluded)
    server_seconds = []
    history = []

    for round_num in range(1, NUM_ROUNDS + 1):
        attacking = round_num > CALIBRATION_ROUNDS
        online = [c for c in range(num_clients)
                  if round_num <= CALIBRATION_ROUNDS or drop_rng.random() >= dropout]
        messages, counts = {}, {}
        for c in online:
            mask = assignment == c
            X_c, y_c = X[mask], y[mask]
            if attacking and c in attackers:
                y_c = 1 - y_c
            if shift and c == SHIFT_CLIENT and round_num > SHIFT_ROUND:
                X_c = np.concatenate([X_c, X[shift_rows]])
                y_c = np.concatenate([y_c, y[shift_rows]])
            local_model.set_weights(unflatten(global_vec, like))
            local_model.fit(X_c, y_c, epochs=LOCAL_EPOCHS, batch_size=BATCH_SIZE, verbose=0)
            delta = flatten(local_model.get_weights()) - global_vec
            counts[c] = int(mask.sum())
            messages[c] = (delta if policy == "none"
                           else pack(c, round_num, counts[c], delta, keys[c], fingerprinter))

        t0 = time.perf_counter()
        if policy == "none":
            accepted = messages
            if attacking:
                decisions += [(round_num, c, c in attackers, False) for c in messages]
        else:
            deltas, fingerprints = {}, {}
            for c, m in messages.items():
                header, delta, reason = unpack(m, keys, fingerprinter)
                assert reason is None, reason
                deltas[c], fingerprints[c] = delta, header["fp"]
            scores = scorer.score_round(fingerprints)
            if not attacking:
                for c in fingerprints:
                    calibrator.add(c, scores[c], fingerprints[c])
                if round_num == CALIBRATION_ROUNDS:
                    calibrator.fit()
                accepted = deltas
            else:
                passed = {c: d for c, d in deltas.items()
                          if not is_flagged(scores[c], calibrator.threshold_for(c))}
                flagged = {c: d for c, d in deltas.items() if c not in passed}
                rescued = second_check(passed, flagged, TRIM_FRACTION)
                accepted = {**passed, **rescued}
                decisions += [(round_num, c, c in attackers, c not in accepted) for c in deltas]
            scorer.remember(fingerprints)

        if accepted:
            sub = {c: counts[c] for c in accepted}
            if policy == "none":
                total = sum(sub.values())
                weights = {c: n / total for c, n in sub.items()}
            else:
                weights = capped_weights(sub, WEIGHT_CAP_FACTOR)
            global_vec = global_vec + sum(accepted[c] * weights[c] for c in accepted)
        server_seconds.append(time.perf_counter() - t0)
        global_model.set_weights(unflatten(global_vec, like))
        history.append(evaluate(global_model, data)["accuracy"])

    mal = [d[3] for d in decisions if d[2]]
    hon = [d[3] for d in decisions if not d[2]]
    shifted = [d[3] for d in decisions if d[1] == SHIFT_CLIENT and d[0] > SHIFT_ROUND]
    others_after = [d[3] for d in decisions
                    if not d[2] and d[1] != SHIFT_CLIENT and d[0] > SHIFT_ROUND]
    return {
        "num_clients": num_clients,
        "attackers": sorted(int(a) for a in attackers),
        "final_accuracy": history[-1],
        "accuracy_by_round": history,
        "detection_rate": float(np.mean(mal)) if mal else None,
        "false_positive_rate": float(np.mean(hon)) if hon else None,
        "shifted_client_excluded_rate": float(np.mean(shifted)) if shifted else None,
        "other_honest_excluded_after_shift": float(np.mean(others_after)) if others_after else None,
        "mean_server_ms_per_round": 1000 * float(np.mean(server_seconds[CALIBRATION_ROUNDS:])),
    }


def plan():
    """Every run as (experiment, setting, policy, seed)."""
    runs = []
    for seed in range(NUM_SEEDS):
        for p in DROPOUT_RATES:
            for policy in ("none", "v2"):
                runs.append(("dropout", p, policy, seed))
        for policy in ("v2", "v2_mondrian"):
            runs.append(("shift", SHIFT_TYPE, policy, seed))
        for k in SCALE_FACTORS:
            for policy in ("v2", "v2_mondrian"):
                runs.append(("scale", k, policy, seed))
    return runs


def summarize(runs: list) -> dict:
    out = {}
    keys = ("final_accuracy", "detection_rate", "false_positive_rate",
            "shifted_client_excluded_rate", "other_honest_excluded_after_shift",
            "mean_server_ms_per_round")
    groups = {}
    for r in runs:
        groups.setdefault((r["experiment"], str(r["setting"]), r["policy"]), []).append(r)
    for (exp, setting, policy), rs in sorted(groups.items()):
        e = {"runs": len(rs)}
        for k in keys:
            vals = [r[k] for r in rs if r[k] is not None]
            if vals:
                e[f"{k}_mean"], e[f"{k}_std"] = float(np.mean(vals)), float(np.std(vals))
        out.setdefault(exp, {}).setdefault(setting, {})[policy] = e

    tests = {}
    for exp, setting, metric in [("shift", SHIFT_TYPE, "shifted_client_excluded_rate")] + \
            [("scale", str(k), m) for k in SCALE_FACTORS for m in ("detection_rate", "false_positive_rate")]:
        a = {r["seed"]: r[metric] for r in runs if r["experiment"] == exp
             and str(r["setting"]) == setting and r["policy"] == "v2"}
        b = {r["seed"]: r[metric] for r in runs if r["experiment"] == exp
             and str(r["setting"]) == setting and r["policy"] == "v2_mondrian"}
        seeds = sorted(set(a) & set(b))
        if len(seeds) < 2:
            continue
        x, z = np.array([a[s] for s in seeds]), np.array([b[s] for s in seeds])
        res = {"n": len(seeds), "global_minus_mondrian": float(np.mean(x - z))}
        if not np.allclose(x, z):
            t, p = stats.ttest_rel(x, z)
            res.update(t=float(t), p_value=float(p))
        tests[f"{exp}/{setting}/{metric}"] = res
    out["paired_tests_global_vs_mondrian"] = tests
    return out


def save(runs: list):
    config = {"num_seeds": NUM_SEEDS, "num_rounds": NUM_ROUNDS,
              "calibration_rounds": CALIBRATION_ROUNDS, "attacker_fraction": ATTACKER_FRACTION,
              "dropout_rates": DROPOUT_RATES, "scale_factors": SCALE_FACTORS,
              "shift": {"round": SHIFT_ROUND, "router": SHIFT_CLIENT + 1,
                        "type": SHIFT_TYPE, "ratio": SHIFT_RATIO}}
    tmp = RESULTS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"config": config, "summary": summarize(runs), "runs": runs}, f, indent=2)
    os.replace(tmp, RESULTS_PATH)


def main():
    data = load_dataset("flnet")
    base = data["assignment"]
    runs = []
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            runs = json.load(f)["runs"]
        print(f"Resuming: {len(runs)} runs already done.")
    done = {(r["experiment"], str(r["setting"]), r["policy"], r["seed"]) for r in runs}

    todo = plan()
    started = time.time()
    for i, (exp, setting, policy, seed) in enumerate(todo, 1):
        if (exp, str(setting), policy, seed) in done:
            continue
        if exp == "dropout":
            assignment = base
            attackers = choose_attackers(10, seed)
            r = run_once(data, assignment, policy, seed, attackers, dropout=setting)
        elif exp == "shift":
            r = run_once(data, base, policy, seed, set(), shift=True)
        else:
            assignment = split_clients(base, setting, seed)
            attackers = choose_attackers(int(assignment.max()) + 1, seed)
            r = run_once(data, assignment, policy, seed, attackers)
        r.update(experiment=exp, setting=setting, policy=policy, seed=seed)
        runs.append(r)
        save(runs)
        extra = "" if policy == "none" else (
            f" caught {r['detection_rate']:.2f} FPR {r['false_positive_rate']:.3f}"
            if r["detection_rate"] is not None else
            f" shifted-router excluded {r['shifted_client_excluded_rate']:.2f}")
        print(f"[{i}/{len(todo)}] {exp:7s} {str(setting):10s} {policy:11s} seed {seed} "
              f"clients {r['num_clients']:2d} acc {r['final_accuracy']:.4f}{extra} "
              f"server {r['mean_server_ms_per_round']:.0f} ms/round "
              f"[{(time.time() - started) / 60:.1f} min]", flush=True)

    print("\n" + json.dumps(summarize(runs), indent=2))
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
