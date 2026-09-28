"""
Phase 8 — Krypsis custom communication protocol (security-fused update
exchange). Implements README > "Custom Protocol Design".

Every round, each client sends its model update d = w_local - w_global as

    message = header (JSON) + payload (raw float32 bytes of d) + tag

  - payload:  the flattened update, float32.
  - header:   client id, round, sample count, and a compact FINGERPRINT of
              the update: global L2 norm, one L2 norm per Dense layer, and a
              SKETCH_DIM-dimensional random projection ("sketch") of d. The
              projection matrix comes from a public seed, so client and
              server compute identical sketches.
  - tag:      HMAC-SHA256 over header + payload with the client's pre-shared
              key.

Server-side, before any aggregation:

  1. Verify the HMAC. Mismatch -> reject (corrupted/tampered in transit).
  2. Verify the fingerprint really describes the payload (recompute it);
     mismatch -> reject. A client cannot lie about its own fingerprint.
  3. Score the update with three cheap anomaly scores, all computed from the
     fingerprint only:
       - norm score:      |log(||d|| / median ||d|| of this round)| —
                          update much larger/smaller than the others
                          (relative to the round, because every client's
                          update shrinks as training converges)
       - consensus score: 1 - cos(sketch, coordinate-wise median sketch of
                          this round) — points away from the other clients
       - history score:   1 - cos(sketch, this client's previous sketch) —
                          behaves unlike itself
     Each score is then robustly standardized across the round's clients,
     z = (score - median) / (1.4826 * MAD), and the update is flagged if any
     z exceeds its threshold. Standardizing matters: once the model
     converges every honest update becomes small and noisy, so the raw
     scores of *all* clients drift upward and thresholds fit on early
     rounds would flag everyone. Relative to the round, they stay stable.

Thresholds are calibrated on the first rounds (assumed clean), in one of
two ways — the project's research question:

  - GlobalCalibrator:   one threshold per score, over all clients pooled.
  - MondrianCalibrator: clients are clustered (k-means on their mean
    calibration-round sketch — no raw data or labels leave the clients) and
    each cluster gets its own thresholds (Mondrian conformal style).

Thresholds are conformal quantiles: the ceil((n+1)(1-alpha))-th smallest of
n calibration scores, so an honest update exceeds each one with probability
<= alpha under exchangeability. A Mondrian cluster with too few calibration
scores for that rank falls back to the global threshold.
"""

import hashlib
import hmac
import json
import math

import numpy as np
from sklearn.cluster import KMeans

SKETCH_DIM = 64
SKETCH_SEED = 2023
SCORE_NAMES = ("norm", "consensus", "history")


# ---------------------------------------------------------------- helpers

def flatten(weights: list) -> np.ndarray:
    return np.concatenate([w.ravel() for w in weights]).astype(np.float32)


def unflatten(vector: np.ndarray, like: list) -> list:
    out, start = [], 0
    for w in like:
        out.append(vector[start:start + w.size].reshape(w.shape))
        start += w.size
    return out


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b) / denom if denom > 0 else 0.0


class Fingerprinter:
    """Computes the fingerprint of a flattened update. `layer_slices` group
    the flat vector by Dense layer (kernel + bias)."""

    def __init__(self, weight_shapes: list):
        sizes = [int(np.prod(s)) for s in weight_shapes]
        self.dim = sum(sizes)
        # Kernel and bias arrays alternate for Dense layers.
        bounds = np.cumsum([0] + sizes)
        self.layer_slices = [slice(bounds[i], bounds[i + 2])
                             for i in range(0, len(sizes), 2)]
        rng = np.random.default_rng(SKETCH_SEED)
        self.projection = (rng.standard_normal((SKETCH_DIM, self.dim))
                           / math.sqrt(SKETCH_DIM)).astype(np.float32)

    def compute(self, delta: np.ndarray) -> dict:
        return {
            "l2": float(np.linalg.norm(delta)),
            "layer_l2": [float(np.linalg.norm(delta[s])) for s in self.layer_slices],
            "sketch": (self.projection @ delta).tolist(),
        }


# ---------------------------------------------------------------- wire format

def pack(client_id: int, round_num: int, num_samples: int, delta: np.ndarray,
         key: bytes, fingerprinter: Fingerprinter) -> bytes:
    """Client side: build one protocol message."""
    header = json.dumps({
        "client": client_id,
        "round": round_num,
        "n": num_samples,
        "fp": fingerprinter.compute(delta),
    }, separators=(",", ":")).encode()
    payload = delta.astype(np.float32).tobytes()
    tag = hmac.new(key, header + payload, hashlib.sha256).digest()
    return len(header).to_bytes(4, "big") + header + payload + tag


def unpack(message: bytes, keys: dict, fingerprinter: Fingerprinter):
    """Server side: verify and decode one message. Returns
    (header, delta, None) on success or (header_or_None, None, reason)."""
    header_len = int.from_bytes(message[:4], "big")
    header_bytes = message[4:4 + header_len]
    payload = message[4 + header_len:-32]
    tag = message[-32:]
    try:
        header = json.loads(header_bytes)
        key = keys[header["client"]]
    except (ValueError, KeyError, TypeError):
        return None, None, "malformed"
    expected = hmac.new(key, header_bytes + payload, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        return header, None, "bad_tag"

    delta = np.frombuffer(payload, dtype=np.float32)
    if delta.size != fingerprinter.dim:
        return header, None, "bad_size"
    actual = fingerprinter.compute(delta)
    claimed = header["fp"]
    if (not np.isclose(actual["l2"], claimed["l2"], rtol=1e-4, atol=1e-6)
            or not np.allclose(actual["sketch"], claimed["sketch"], rtol=1e-3, atol=1e-5)):
        return header, None, "fingerprint_mismatch"
    return header, delta, None


def http_json_size(delta: np.ndarray) -> int:
    """Size of the same update sent the 'generic HTTP/JSON' way (a JSON list
    of floats), as the communication baseline."""
    return len(json.dumps(delta.tolist(), separators=(",", ":")).encode())


# ---------------------------------------------------------------- scoring

MIN_SCALE = 1e-3


def standardize(scores: dict) -> dict:
    """Robust z-score of each score across this round's clients."""
    out = {c: {} for c in scores}
    for name in SCORE_NAMES:
        present = {c: s[name] for c, s in scores.items() if s[name] is not None}
        if len(present) < 3:
            for c in scores:
                out[c][name] = None
            continue
        values = np.array(list(present.values()))
        median = float(np.median(values))
        scale = max(1.4826 * float(np.median(np.abs(values - median))), MIN_SCALE)
        for c in scores:
            out[c][name] = ((present[c] - median) / scale) if c in present else None
    return out


class AnomalyScorer:
    """Turns a round's fingerprints into per-client anomaly scores. Keeps
    each client's previous sketch for the history score."""

    def __init__(self):
        self.prev_sketch = {}

    def score_round(self, fingerprints: dict) -> dict:
        sketches = {c: np.asarray(fp["sketch"]) for c, fp in fingerprints.items()}
        # Medians, not means: a few poisoned updates cannot drag the
        # consensus toward themselves.
        consensus = np.median(np.stack(list(sketches.values())), axis=0)
        median_norm = float(np.median([fp["l2"] for fp in fingerprints.values()]))
        scores = {}
        for c, fp in fingerprints.items():
            prev = self.prev_sketch.get(c)
            scores[c] = {
                "norm": abs(math.log(max(fp["l2"], 1e-12) / max(median_norm, 1e-12))),
                "consensus": 1.0 - cosine(sketches[c], consensus),
                # No history yet on a client's first message.
                "history": 1.0 - cosine(sketches[c], prev) if prev is not None else None,
            }
        return standardize(scores)

    def remember(self, fingerprints: dict):
        for c, fp in fingerprints.items():
            self.prev_sketch[c] = np.asarray(fp["sketch"])


def conformal_threshold(scores: list, alpha: float) -> float:
    n = len(scores)
    rank = math.ceil((n + 1) * (1 - alpha))
    if rank > n:
        return math.inf
    return float(np.sort(scores)[rank - 1])


class GlobalCalibrator:
    """One threshold per score, fit on all clients' calibration scores."""

    name = "global"

    def __init__(self, alpha: float):
        self.alpha = alpha
        self.calib = {s: [] for s in SCORE_NAMES}
        self.thresholds = None

    def add(self, client: int, scores: dict, fingerprint: dict):
        for s in SCORE_NAMES:
            if scores[s] is not None:
                self.calib[s].append(scores[s])

    def fit(self):
        self.thresholds = {s: conformal_threshold(v, self.alpha)
                           for s, v in self.calib.items()}

    def threshold_for(self, client: int) -> dict:
        return self.thresholds

    def describe(self) -> dict:
        return {"thresholds": self.thresholds}


class MondrianCalibrator:
    """Clusters clients by their mean calibration-round sketch, then fits one
    set of thresholds per cluster from that cluster's scores only."""

    name = "mondrian"

    def __init__(self, alpha: float, num_clusters: int, seed: int):
        self.alpha = alpha
        self.fallback = GlobalCalibrator(alpha)
        self.num_clusters = num_clusters
        self.seed = seed
        self.calib = {}      # client -> {score: [values]}
        self.sketches = {}   # client -> [sketches]
        self.cluster_of = None
        self.thresholds = None

    def add(self, client: int, scores: dict, fingerprint: dict):
        per = self.calib.setdefault(client, {s: [] for s in SCORE_NAMES})
        for s in SCORE_NAMES:
            if scores[s] is not None:
                per[s].append(scores[s])
        self.fallback.add(client, scores, fingerprint)
        sketch = np.asarray(fingerprint["sketch"])
        self.sketches.setdefault(client, []).append(sketch / (np.linalg.norm(sketch) + 1e-12))

    def fit(self):
        clients = sorted(self.sketches)
        profiles = np.stack([np.mean(self.sketches[c], axis=0) for c in clients])
        k = min(self.num_clusters, len(clients))
        labels = KMeans(n_clusters=k, n_init=10, random_state=self.seed).fit_predict(profiles)
        self.cluster_of = {c: int(l) for c, l in zip(clients, labels)}
        self.fallback.fit()
        self.thresholds = {}
        for cluster in range(k):
            members = [c for c in clients if self.cluster_of[c] == cluster]
            self.thresholds[cluster] = {}
            for s in SCORE_NAMES:
                t = conformal_threshold(
                    [v for c in members for v in self.calib[c][s]], self.alpha)
                self.thresholds[cluster][s] = (
                    t if math.isfinite(t) else self.fallback.thresholds[s])

    def threshold_for(self, client: int) -> dict:
        return self.thresholds[self.cluster_of[client]]

    def describe(self) -> dict:
        return {"clusters": self.cluster_of,
                "thresholds": {str(k): v for k, v in self.thresholds.items()}}


def is_flagged(scores: dict, thresholds: dict) -> bool:
    return any(scores[s] is not None and scores[s] > thresholds[s]
               for s in SCORE_NAMES)
