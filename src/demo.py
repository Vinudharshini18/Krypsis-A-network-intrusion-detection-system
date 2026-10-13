"""
Quick demo — the whole Krypsis pipeline in about 3 minutes, with readable
output. Meant for watching the system work (e.g. live in a presentation);
the full, repeated experiments are the other scripts in src/.

  1. The data: FLNET2023's 10 routers and what each one sees.
  2. One protocol message: its size, and what happens when a byte is
     changed in transit.
  3. A short federated run with 2 attacking routers, with and without the
     Krypsis protocol, printing every round: who was flagged, and accuracy.
  4. The headline results of the full experiments (from results/*.json).

Needs the prepared data (src/preprocess.py + src/client_simulation.py).

Run: venv\\Scripts\\python.exe src\\demo.py
"""

import json
import os

import numpy as np

from defense_experiment import evaluate, load_dataset, seed_everything
from model import build_model
from protocol import (AnomalyScorer, GlobalCalibrator, capped_weights, flatten,
                      http_json_size, is_flagged, pack, second_check, unflatten,
                      unpack)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

ROUNDS = 6
CALIBRATION_ROUNDS = 3
ATTACKERS = {1, 5}          # routers 2 and 6 (0-based ids)
SEED = 0


def heading(text):
    print("\n" + "=" * 70 + f"\n  {text}\n" + "=" * 70)


def show_data(data):
    heading("STEP 1 - The data: FLNET2023, one federated client per router")
    a, y = data["assignment"], data["y"]
    print(f"Training flows: {len(y):,}   Test flows: {len(data['y_test']):,}   "
          f"Features per flow: {data['X'].shape[1]}")
    print("\nRouter   Flows     Attack %   Traffic types seen")
    for c in range(int(a.max()) + 1):
        mask = a == c
        types = sorted(set(data["train_type"][mask]) - {"Normal"})
        print(f"  {c + 1:2d}   {mask.sum():8,}   {100 * y[mask].mean():6.1f}%    "
              f"Normal + {', '.join(types)}")


def show_message(data, rng):
    heading("STEP 2 - One Krypsis protocol message")
    fp = data["fingerprinter"]
    key = rng.bytes(32)
    delta = (rng.standard_normal(fp.dim) * 1e-3).astype(np.float32)
    msg = pack(0, 1, 1000, delta, key, fp)
    print(f"Model update: {fp.dim:,} numbers = {4 * fp.dim:,} bytes")
    print(f"Krypsis message (header + fingerprint + update + HMAC tag): {len(msg):,} bytes "
          f"(+{len(msg) - 4 * fp.dim:,})")
    print(f"Same update as plain HTTP/JSON: {http_json_size(delta):,} bytes")

    _, _, reason = unpack(msg, {0: key}, fp)
    print(f"\nServer checks the original message   -> {'ACCEPTED' if reason is None else reason}")
    tampered = bytearray(msg)
    tampered[len(msg) // 2] ^= 0xFF
    _, _, reason = unpack(bytes(tampered), {0: key}, fp)
    print(f"Server checks it with ONE byte changed -> REJECTED ({reason})")


def federated(data, use_protocol):
    seed_everything(SEED)
    rng = np.random.default_rng(SEED)
    a = data["assignment"]
    n_clients = int(a.max()) + 1
    model, local = build_model(data["X"].shape[1]), build_model(data["X"].shape[1])
    like = model.get_weights()
    g = flatten(like)
    fp = data["fingerprinter"]
    keys = {c: rng.bytes(32) for c in range(n_clients)}
    scorer, calib = AnomalyScorer(), GlobalCalibrator(0.05)

    for rnd in range(1, ROUNDS + 1):
        attacking = rnd > CALIBRATION_ROUNDS
        deltas, counts, fps = {}, {}, {}
        for c in range(n_clients):
            mask = a == c
            y_c = data["y"][mask]
            if attacking and c in ATTACKERS:
                y_c = 1 - y_c                      # label flipping
            local.set_weights(unflatten(g, like))
            local.fit(data["X"][mask], y_c, epochs=1, batch_size=256, verbose=0)
            d = flatten(local.get_weights()) - g
            counts[c] = int(mask.sum())
            if use_protocol:
                header, d, _ = unpack(pack(c, rnd, counts[c], d, keys[c], fp), keys, fp)
                fps[c] = header["fp"]
            deltas[c] = d

        note = ""
        accepted = deltas
        if use_protocol:
            scores = scorer.score_round(fps)
            if not attacking:
                for c in fps:
                    calib.add(c, scores[c], fps[c])
                if rnd == CALIBRATION_ROUNDS:
                    calib.fit()
                note = "calibrating thresholds"
            else:
                passed = {c: d for c, d in deltas.items()
                          if not is_flagged(scores[c], calib.threshold_for(c))}
                flagged = {c: d for c, d in deltas.items() if c not in passed}
                rescued = second_check(passed, flagged, 0.2)
                accepted = {**passed, **rescued}
                blocked = sorted(c + 1 for c in deltas if c not in accepted)
                note = (f"blocked routers {blocked}" if blocked else "nothing blocked")
                if rescued:
                    note += f", rescued {sorted(c + 1 for c in rescued)}"
            scorer.remember(fps)
            w = capped_weights({c: counts[c] for c in accepted}, 1.5)
        else:
            total = sum(counts[c] for c in accepted)
            w = {c: counts[c] / total for c in accepted}
        g = g + sum(accepted[c] * w[c] for c in accepted)
        model.set_weights(unflatten(g, like))
        acc = evaluate(model, data)["accuracy"]
        phase = "ATTACK" if attacking else "clean "
        print(f"  Round {rnd} [{phase}] accuracy {100 * acc:6.2f}%   {note}", flush=True)
    return acc


def show_saved_results():
    heading("STEP 4 - Headline results of the full experiments (results/*.json)")

    def load(name):
        path = os.path.join(RESULTS_DIR, name)
        return json.load(open(path)) if os.path.exists(path) else None

    c = load("centralized_baseline.json")
    r = load("federated_router.json")
    if c and r:
        print(f"Binary detection: centralized {100 * c['accuracy']:.2f}%, "
              f"federated over 10 routers {100 * r[-1]['accuracy']:.2f}%")
    d = load("defense_experiment.json")
    if d:
        s = d["summary"]
        nl, nb = s["nslkdd/label_flip"], s["nslkdd/backdoor"]
        print(f"NSL-KDD label flipping: accuracy {100 * nl['none']['accuracy_mean']:.1f}% "
              f"(no defense) -> {100 * nl['v2']['accuracy_mean']:.1f}% (protocol)")
        print(f"NSL-KDD backdoor success: {100 * nb['none']['backdoor_asr_mean']:.1f}% "
              f"-> {100 * nb['v2']['backdoor_asr_mean']:.1f}%")
    m = load("multiclass.json")
    if m:
        print(f"Multi-class (11 types) macro-F1: centralized {m['centralized']['macro_f1']:.2f}, "
              f"IID {m['federated_iid']['macro_f1']:.2f}, "
              f"real routers {m['federated_router']['macro_f1']:.2f}")
    p = load("protocol_experiment.json")
    if p:
        g, mo = p["summary"]["global"], p["summary"]["mondrian"]
        print(f"Global vs Mondrian thresholds: caught {100 * g['detection_rate_mean']:.1f}% vs "
              f"{100 * mo['detection_rate_mean']:.1f}% - not significantly different")
    print(f"\nFigures: {os.path.join(RESULTS_DIR, 'figures')}")


def main():
    data = load_dataset("flnet")
    rng = np.random.default_rng(SEED)
    show_data(data)
    show_message(data, rng)

    heading(f"STEP 3 - Federated training, routers {sorted(c + 1 for c in ATTACKERS)} "
            f"attack after round {CALIBRATION_ROUNDS}")
    print("\n(a) Plain FedAvg, no protection:")
    plain = federated(data, use_protocol=False)
    print("\n(b) With the Krypsis protocol:")
    protected = federated(data, use_protocol=True)
    print(f"\nFinal accuracy: {100 * plain:.2f}% without protection, "
          f"{100 * protected:.2f}% with the protocol")

    show_saved_results()


if __name__ == "__main__":
    main()
