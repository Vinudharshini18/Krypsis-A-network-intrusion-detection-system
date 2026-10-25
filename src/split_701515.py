"""
70 / 15 / 15 re-split of FLNET2023 (train / validation / test).

Why: the first version used the dataset's own split (router files for
training, the separate TEST capture for testing, about 88 / 12). That split
gave 100% accuracy, and 10.8% of the test flows were exact copies of
training flows, so it could not show whether the model overfits. This
script builds a fairer split:

  1. Load and clean the router files exactly as src/preprocess.py does
     (same 10% per-file sampling, same seed, same dropped columns).
  2. Remove exact duplicate flows, so one flow can never end up in two sets.
  3. Inside each router, split its flows 70% train / 15% validation /
     15% test, stratified by attack type, so every set keeps that router's
     traffic mix. Each router still trains only on its own 70%.
  4. Fit the scaler on the 70% train rows only.
  5. Keep the dataset's separate TEST capture as an extra "new capture"
     test, with any flow already present in our data removed.

Output goes to data/processed_701515/, so the original data/processed/ (and
every result built from it) stays untouched.

Run: venv\\Scripts\\python.exe src\\split_701515.py
"""

import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

from client_simulation import split_iid
from preprocess import (DROP_COLUMNS, LABEL_COLUMN, SEED, build_binary_label,
                        clean, load_split, signed_log1p)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "processed_701515")

TRAIN_SHARE, VAL_SHARE, TEST_SHARE = 0.70, 0.15, 0.15
# Attack types with fewer rows than this inside one router are stratified
# together with the router's other rare rows of the same binary label;
# stratifying on a class with 1-2 rows is impossible.
MIN_STRATUM = 20


def strata(attack_type: pd.Series, label: pd.Series) -> pd.Series:
    counts = attack_type.map(attack_type.value_counts())
    rare = np.where(label == 1, "rare_attack", "rare_normal")
    return pd.Series(np.where(counts >= MIN_STRATUM, attack_type, rare),
                     index=attack_type.index)


def stratified(idx, test_size, key, label, seed):
    """Stratify by attack type; if a stratum is still too small, fall back
    to stratifying by the binary label."""
    try:
        return train_test_split(idx, test_size=test_size, stratify=key, random_state=seed)
    except ValueError:
        return train_test_split(idx, test_size=test_size, stratify=label, random_state=seed)


def split_router(df: pd.DataFrame, seed: int):
    """Split one router's rows 70/15/15; returns three index arrays."""
    label = build_binary_label(df)
    key = strata(df[LABEL_COLUMN].astype(str), label)
    idx = df.index.to_numpy()
    train_idx, rest_idx = stratified(idx, VAL_SHARE + TEST_SHARE, key, label, seed)
    rest_key = strata(df.loc[rest_idx, LABEL_COLUMN].astype(str), label.loc[rest_idx])
    val_idx, test_idx = stratified(rest_idx, TEST_SHARE / (VAL_SHARE + TEST_SHARE),
                                   rest_key, label.loc[rest_idx], seed)
    return train_idx, val_idx, test_idx


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(SEED)
    # Same calls, same order, same seed as preprocess.py -> the same sampled rows.
    print("Loading router files...")
    data = load_split(test=False, rng=rng)
    print("Loading the separate TEST capture...")
    capture = load_split(test=True, rng=rng)

    features = [c for c in data.columns if c not in DROP_COLUMNS + [LABEL_COLUMN, "router"]]
    data = clean(data, features)
    capture = clean(capture, features)

    report = {"sampled_router_flows": int(len(data))}

    # 1. Exact duplicates (same features and same label) -> keep one copy.
    before = len(data)
    data = data.drop_duplicates(subset=features + [LABEL_COLUMN]).reset_index(drop=True)
    report["duplicates_removed"] = int(before - len(data))
    # Same features but different labels: the flow cannot be classified
    # consistently and would sit on both sides of the split. Drop them.
    conflict = data.duplicated(subset=features, keep=False)
    report["conflicting_label_flows_removed"] = int(conflict.sum())
    data = data.loc[~conflict].reset_index(drop=True)
    report["flows_after_dedup"] = int(len(data))
    print(f"  removed {report['duplicates_removed']} exact duplicates and "
          f"{report['conflicting_label_flows_removed']} same-features-different-label flows "
          f"-> {len(data)} unique flows")

    # 2. 70/15/15 inside each router.
    parts = {"train": [], "val": [], "test": []}
    for router, group in data.groupby("router"):
        tr, va, te = split_router(group, SEED)
        parts["train"].append(tr)
        parts["val"].append(va)
        parts["test"].append(te)
    parts = {k: np.sort(np.concatenate(v)) for k, v in parts.items()}
    assert not (set(parts["train"]) & set(parts["val"]) or set(parts["train"]) & set(parts["test"])
                or set(parts["val"]) & set(parts["test"]))

    # Constant columns are judged on the training rows only.
    train_df = data.loc[parts["train"]]
    constant = [c for c in features if train_df[c].nunique() <= 1]
    features = [c for c in features if c not in constant]
    print(f"  dropped {len(constant)} constant columns -> {len(features)} features")

    # 3. The extra test: the TEST capture minus any flow already in our data.
    seen = pd.MultiIndex.from_frame(data[features])
    in_data = pd.MultiIndex.from_frame(capture[features]).isin(seen)
    report["capture_flows"] = int(len(capture))
    report["capture_flows_removed_as_seen"] = int(in_data.sum())
    capture = capture.loc[~in_data].reset_index(drop=True)

    # 4. Scale: fit on train only.
    scaler = MinMaxScaler()
    scaler.fit(signed_log1p(train_df[features].to_numpy(np.float64)))

    def transform(df):
        x = scaler.transform(signed_log1p(df[features].to_numpy(np.float64)))
        return np.clip(x, 0.0, 1.0).astype(np.float32)

    routers = np.unique(data["router"])
    report["sets"] = {}
    for name, idx in parts.items():
        df = data.loc[idx]
        X, y = transform(df), build_binary_label(df).to_numpy()
        client = np.searchsorted(routers, df["router"].to_numpy())
        np.save(os.path.join(OUT_DIR, f"X_{name}.npy"), X)
        np.save(os.path.join(OUT_DIR, f"y_{name}.npy"), y)
        np.save(os.path.join(OUT_DIR, f"{name}_client.npy"), client)
        df[[LABEL_COLUMN]].rename(columns={LABEL_COLUMN: "attack_type"}).to_csv(
            os.path.join(OUT_DIR, f"{name}_attack_type.csv"), index=False)
        report["sets"][name] = {
            "flows": int(len(y)), "share": round(len(y) / len(data), 4),
            "attack_share": round(float(y.mean()), 4),
            "per_router_flows": {int(r): int((client == i).sum()) for i, r in enumerate(routers)},
            "per_router_attack_share": {int(r): round(float(y[client == i].mean()), 4)
                                        for i, r in enumerate(routers)},
        }
        print(f"  {name:5s}: {len(y):7d} flows ({100 * len(y) / len(data):.1f}%), "
              f"{100 * y.mean():.1f}% attack")

    Xc, yc = transform(capture), build_binary_label(capture).to_numpy()
    np.save(os.path.join(OUT_DIR, "X_capture.npy"), Xc)
    np.save(os.path.join(OUT_DIR, "y_capture.npy"), yc)
    report["sets"]["capture"] = {"flows": int(len(yc)), "attack_share": round(float(yc.mean()), 4)}
    print(f"  extra TEST capture: {len(yc)} flows "
          f"({report['capture_flows_removed_as_seen']} removed as already seen)")

    # Client assignments for the training rows (router = natural client; IID = control).
    train_client = np.load(os.path.join(OUT_DIR, "train_client.npy"))
    np.save(os.path.join(OUT_DIR, "client_assignment_router.npy"), train_client)
    np.save(os.path.join(OUT_DIR, "client_assignment_iid.npy"),
            split_iid(len(train_client), len(routers)))

    joblib.dump(scaler, os.path.join(OUT_DIR, "scaler.joblib"))
    with open(os.path.join(OUT_DIR, "feature_names.txt"), "w") as f:
        f.write("\n".join(features))
    with open(os.path.join(OUT_DIR, "split_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved to {OUT_DIR}")


if __name__ == "__main__":
    main()
