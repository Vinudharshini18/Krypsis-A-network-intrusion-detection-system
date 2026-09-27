"""
Phase 3 — Preprocessing for the FLNET2023 dataset.

FLNET2023 (Kumar et al., MILCOM 2023) is flow data (CICFlowMeter features)
captured at 10 routers of an emulated network. Raw layout, after running
src/download_flnet2023.py:

  data/FLNET2023/<Category>/CSV/Dataset-<router>[-<variant>].csv   (training)
  data/FLNET2023/<Category>/<Attack>/CSV/Dataset-<router>.csv      (Web only)
  data/FLNET2023/TEST/CSV/<attack>.csv                             (test set)

Every training file comes from exactly one router, so the router number in
the filename is kept as each row's *natural* federated client ID — the
property that makes this dataset a better fit for FL than NSL-KDD, where
client heterogeneity had to be simulated.

Steps: load (with per-file subsampling, see SAMPLE_FRACTION), drop
identifier columns, clean inf/NaN, log-scale + min-max scale numeric
features (fit on train only), build a binary (normal vs attack) label.
Saves arrays to data/processed/ for the later phases.

Run: venv\\Scripts\\python.exe src\\preprocess.py
"""

import glob
import os
import re

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "FLNET2023")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")

# The full CSV set is ~4.8M flows (~3.2 GB), dominated by a few huge DDoS/DoS
# captures. Training an MLP (and 10 federated clients x many rounds) on all
# of it is impractical on a laptop, so each file is uniformly subsampled.
# MIN_ROWS_PER_FILE keeps the small attack captures (SQL injection, XSS, ...)
# from shrinking to a handful of rows. Proportions between files are kept
# otherwise, so each router's class imbalance is still realistic.
SAMPLE_FRACTION = 0.10
MIN_ROWS_PER_FILE = 2000
SEED = 42

# Identifier columns, not behavioural features: IPs and timestamps would let
# the model memorise *which host / when* rather than *what the traffic looks
# like* (attackers in the emulation use fixed addresses), and the ephemeral
# source port is random noise. dst_port is kept — it plays the role
# NSL-KDD's "service" column did.
DROP_COLUMNS = ["src_ip", "dst_ip", "src_port", "timestamp"]
LABEL_COLUMN = "label"
NORMAL_LABELS = {"normal", "benign"}

ROUTER_PATTERN = re.compile(r"Dataset-(\d+)", re.IGNORECASE)


def sample_file(path: str, rng: np.random.Generator) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    n = len(df)
    keep = min(n, max(MIN_ROWS_PER_FILE, int(round(n * SAMPLE_FRACTION))))
    if keep < n:
        df = df.iloc[np.sort(rng.choice(n, size=keep, replace=False))]
    return df.reset_index(drop=True)


def load_split(test: bool, rng: np.random.Generator) -> pd.DataFrame:
    if test:
        paths = glob.glob(os.path.join(RAW_DIR, "TEST", "CSV", "*.csv"))
    else:
        paths = [p for p in glob.glob(os.path.join(RAW_DIR, "**", "*.csv"), recursive=True)
                 if os.sep + "TEST" + os.sep not in p]
    if not paths:
        raise FileNotFoundError(
            f"No FLNET2023 CSVs found under {RAW_DIR} — run src/download_flnet2023.py first."
        )

    frames = []
    for path in sorted(paths):
        df = sample_file(path, rng)
        if test:
            df["router"] = -1
        else:
            match = ROUTER_PATTERN.search(os.path.basename(path))
            if match is None:
                raise ValueError(f"Cannot read router number from {path}")
            df["router"] = int(match.group(1))
        rel = os.path.relpath(path, RAW_DIR)
        print(f"  {rel:45s} {len(df):8d} rows  labels: "
              f"{', '.join(df[LABEL_COLUMN].astype(str).unique())}")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def clean(df: pd.DataFrame, feature_columns: list) -> pd.DataFrame:
    # CICFlowMeter emits inf for rate features (bytes/s, pkts/s) on
    # zero-duration flows, and occasional NaNs. Treat both as missing and
    # drop those rows (a small fraction; printed so it stays visible).
    features = df[feature_columns].apply(pd.to_numeric, errors="coerce")
    features = features.replace([np.inf, -np.inf], np.nan)
    bad = features.isna().any(axis=1)
    if bad.any():
        print(f"  dropping {bad.sum()} rows with inf/NaN features "
              f"({100 * bad.mean():.2f}%)")
    df = df.loc[~bad].reset_index(drop=True)
    df[feature_columns] = features.loc[~bad].reset_index(drop=True)
    return df


def signed_log1p(x: np.ndarray) -> np.ndarray:
    # Flow features span many orders of magnitude (durations in µs, byte
    # rates up to ~1e9); a signed log keeps min-max scaling from squashing
    # almost every value into the bottom 0.1% of [0, 1].
    return np.sign(x) * np.log1p(np.abs(x))


def build_binary_label(df: pd.DataFrame) -> pd.Series:
    return (~df[LABEL_COLUMN].astype(str).str.lower().isin(NORMAL_LABELS)).astype(int)


def preprocess():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    rng = np.random.default_rng(SEED)

    print("Loading training files (per-router captures)...")
    train_df = load_split(test=False, rng=rng)
    print("Loading test files (TEST/CSV)...")
    test_df = load_split(test=True, rng=rng)

    feature_columns = [c for c in train_df.columns
                       if c not in DROP_COLUMNS + [LABEL_COLUMN, "router"]]
    missing = set(feature_columns) - set(test_df.columns)
    if missing:
        raise ValueError(f"Test files are missing columns: {sorted(missing)}")

    print("Cleaning...")
    train_df = clean(train_df, feature_columns)
    test_df = clean(test_df, feature_columns)

    # Constant columns (e.g. flag counts that are always 0 in this capture)
    # carry no information; drop them based on the training set only.
    constant = [c for c in feature_columns if train_df[c].nunique() <= 1]
    if constant:
        print(f"  dropping {len(constant)} constant columns: {', '.join(constant)}")
        feature_columns = [c for c in feature_columns if c not in constant]

    y_train = build_binary_label(train_df).to_numpy()
    y_test = build_binary_label(test_df).to_numpy()

    # Fit the scaler on TRAIN ONLY, then transform both — the test set must
    # never influence fitting, or evaluation numbers are optimistic.
    print("Scaling features (signed log1p + min-max)...")
    scaler = MinMaxScaler()
    X_train = scaler.fit_transform(signed_log1p(train_df[feature_columns].to_numpy(np.float64)))
    X_test = scaler.transform(signed_log1p(test_df[feature_columns].to_numpy(np.float64)))
    # Test values outside the training range would fall outside [0, 1].
    X_test = np.clip(X_test, 0.0, 1.0)
    X_train = X_train.astype(np.float32)
    X_test = X_test.astype(np.float32)

    print(f"  Final feature count: {X_train.shape[1]}")
    print(f"  X_train: {X_train.shape}, X_test: {X_test.shape}")
    print(f"  Train class balance -> normal: {(y_train == 0).sum()}, "
          f"attack: {(y_train == 1).sum()} "
          f"({100 * y_train.mean():.1f}% attack)")
    print(f"  Test class balance  -> normal: {(y_test == 0).sum()}, "
          f"attack: {(y_test == 1).sum()} "
          f"({100 * y_test.mean():.1f}% attack)")

    np.save(os.path.join(PROCESSED_DIR, "X_train.npy"), X_train)
    np.save(os.path.join(PROCESSED_DIR, "y_train.npy"), y_train)
    np.save(os.path.join(PROCESSED_DIR, "X_test.npy"), X_test)
    np.save(os.path.join(PROCESSED_DIR, "y_test.npy"), y_test)
    np.save(os.path.join(PROCESSED_DIR, "train_router.npy"),
            train_df["router"].to_numpy())

    # Original attack names kept for per-attack analysis and the IID split's
    # summary printout.
    train_df[[LABEL_COLUMN]].rename(columns={LABEL_COLUMN: "attack_type"}).to_csv(
        os.path.join(PROCESSED_DIR, "train_attack_type.csv"), index=False
    )
    test_df[[LABEL_COLUMN]].rename(columns={LABEL_COLUMN: "attack_type"}).to_csv(
        os.path.join(PROCESSED_DIR, "test_attack_type.csv"), index=False
    )

    joblib.dump(scaler, os.path.join(PROCESSED_DIR, "scaler.joblib"))
    with open(os.path.join(PROCESSED_DIR, "feature_names.txt"), "w") as f:
        f.write("\n".join(feature_columns))

    print(f"\nSaved processed data to {PROCESSED_DIR}")


if __name__ == "__main__":
    preprocess()
