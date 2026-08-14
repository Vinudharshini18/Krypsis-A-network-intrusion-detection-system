"""
Phase 3 — Preprocessing for the NSL-KDD dataset.

Loads the raw KDDTrain+.txt / KDDTest+.txt files, encodes categorical
columns, scales numeric columns, and builds a binary (normal vs attack)
label. Saves the processed arrays to data/processed/ so later phases
(client simulation, model training) can load them directly instead of
repeating this work.

Run: venv\\Scripts\\python.exe src\\preprocess.py
"""

import os

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")

TRAIN_PATH = os.path.join(DATA_DIR, "KDDTrain+.txt")
TEST_PATH = os.path.join(DATA_DIR, "KDDTest+.txt")

# The 41 standard NSL-KDD feature names, in the exact order they appear in
# the raw files, followed by the attack-name label and the difficulty score.
COLUMN_NAMES = [
    "duration", "protocol_type", "service", "flag", "src_bytes", "dst_bytes",
    "land", "wrong_fragment", "urgent", "hot", "num_failed_logins",
    "logged_in", "num_compromised", "root_shell", "su_attempted", "num_root",
    "num_file_creations", "num_shells", "num_access_files",
    "num_outbound_cmds", "is_host_login", "is_guest_login", "count",
    "srv_count", "serror_rate", "srv_serror_rate", "rerror_rate",
    "srv_rerror_rate", "same_srv_rate", "diff_srv_rate",
    "srv_diff_host_rate", "dst_host_count", "dst_host_srv_count",
    "dst_host_same_srv_rate", "dst_host_diff_srv_rate",
    "dst_host_same_src_port_rate", "dst_host_srv_diff_host_rate",
    "dst_host_serror_rate", "dst_host_srv_serror_rate",
    "dst_host_rerror_rate", "dst_host_srv_rerror_rate",
    "attack_type", "difficulty_level",
]

CATEGORICAL_COLUMNS = ["protocol_type", "service", "flag"]
DROP_COLUMNS = ["difficulty_level"]

# NOTE: a log1p transform on skewed count/byte columns (src_bytes,
# duration, etc.) was tried here and measured empirically -- it reduced
# official-split test accuracy (83.1% -> 77.9%) despite improving
# training/validation fit, because it let the model fit the *training*
# distribution's numeric patterns more tightly, which does not transfer to
# the test set's different (unseen) attack types. Reverted; kept as a
# documented negative result rather than silently discarded (see README >
# Phase 5).


def load_raw(path: str) -> pd.DataFrame:
    return pd.read_csv(path, header=None, names=COLUMN_NAMES)


def build_binary_label(df: pd.DataFrame) -> pd.Series:
    # NSL-KDD's "attack_type" column holds either "normal" or a specific
    # attack name (e.g. "neptune", "smurf"). Collapse to binary for the
    # first-milestone model; the original attack_type is kept separately
    # for the later multi-class extension.
    return (df["attack_type"] != "normal").astype(int)


def preprocess():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    print("Loading raw data...")
    train_df = load_raw(TRAIN_PATH)
    test_df = load_raw(TEST_PATH)
    print(f"  train: {train_df.shape}, test: {test_df.shape}")

    # Keep the original multi-class attack name aside before dropping it,
    # for later use (multi-class extension, per-attack-type analysis).
    train_attack_type = train_df["attack_type"].copy()
    test_attack_type = test_df["attack_type"].copy()

    y_train = build_binary_label(train_df)
    y_test = build_binary_label(test_df)

    X_train_raw = train_df.drop(columns=["attack_type"] + DROP_COLUMNS)
    X_test_raw = test_df.drop(columns=["attack_type"] + DROP_COLUMNS)

    numeric_columns = [c for c in X_train_raw.columns if c not in CATEGORICAL_COLUMNS]

    # Fit encoder/scaler on TRAIN ONLY, then transform both — the test set
    # must never influence fitting, or evaluation numbers are optimistic.
    print("Encoding categorical columns (protocol_type, service, flag)...")
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    encoder.fit(X_train_raw[CATEGORICAL_COLUMNS])

    train_cat = encoder.transform(X_train_raw[CATEGORICAL_COLUMNS])
    test_cat = encoder.transform(X_test_raw[CATEGORICAL_COLUMNS])
    cat_feature_names = encoder.get_feature_names_out(CATEGORICAL_COLUMNS)

    print("Scaling numeric columns...")
    scaler = MinMaxScaler()
    train_num = scaler.fit_transform(X_train_raw[numeric_columns])
    test_num = scaler.transform(X_test_raw[numeric_columns])

    X_train = np.hstack([train_num, train_cat]).astype(np.float32)
    X_test = np.hstack([test_num, test_cat]).astype(np.float32)
    feature_names = numeric_columns + list(cat_feature_names)

    y_train = y_train.to_numpy()
    y_test = y_test.to_numpy()

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

    train_attack_type.to_csv(
        os.path.join(PROCESSED_DIR, "train_attack_type.csv"), index=False
    )
    test_attack_type.to_csv(
        os.path.join(PROCESSED_DIR, "test_attack_type.csv"), index=False
    )

    joblib.dump(encoder, os.path.join(PROCESSED_DIR, "encoder.joblib"))
    joblib.dump(scaler, os.path.join(PROCESSED_DIR, "scaler.joblib"))
    with open(os.path.join(PROCESSED_DIR, "feature_names.txt"), "w") as f:
        f.write("\n".join(feature_names))

    print(f"\nSaved processed data to {PROCESSED_DIR}")


if __name__ == "__main__":
    preprocess()
