# Krypsis — Federated Learning-based Network Intrusion Detection with a Custom Communication Protocol

A federated learning based network intrusion detection system using a custom
communication protocol.

## Team Members

| S. No. | Name | Roll No. / Reg. No. |
|---|---|---|
| 1 | RITHIKA K | CB.SC.U4AIE25126 |
| 2 | PRADHANYA S | CB.SC.U4AIE25148 |
| 3 | SATHYA K | CB.SC.U4AIE25154 |
| 4 | VENUDHARSHINI P P | CB.SC.U4AIE25161 |

## Abstract

Network Intrusion Detection Systems (NIDS) are a critical line of defence against
cyberattacks, but conventional approaches typically rely on centralized data
collection, requiring organizations to pool sensitive network traffic on a single
server for model training. This centralization introduces serious privacy risks,
regulatory concerns, and a single point of failure, while also creating
communication bottlenecks when large volumes of traffic data must be transmitted.

This project proposes a Federated Learning-based Network Intrusion Detection
System that trains a shared detection model collaboratively across multiple
distributed clients (e.g., routers, edge devices, or organizational nodes)
without ever transmitting raw traffic data to a central server. Instead, each
client trains a local model on its own data and shares only model updates
(weights/gradients) with a central aggregator, which combines them into a
global model using a federated averaging strategy (FedAvg).

To support this distributed training process efficiently and securely, the
project designs and implements a custom **security-fused communication
protocol** for exchanging model updates between clients and the server. Unlike
generic protocols (HTTP/gRPC) or prior communication-efficiency work — which
treats bandwidth optimization and security as separate concerns, with
malicious-update detection only happening after the full update has been
received and processed by the server — this protocol attaches a lightweight
integrity tag and a compact statistical "fingerprint" to every update at send
time. The server performs a cheap first-pass anomaly check against this
fingerprint before committing to expensive aggregation, allowing tampered,
corrupted, or blatantly poisoned updates to be rejected early and cheaply,
rather than only being caught (or missed) by post-hoc robust aggregation
methods (e.g., Krum, trimmed mean). The resulting system is evaluated on
standard intrusion detection datasets (e.g., NSL-KDD / CICIDS2017) across
multiple simulated clients, measuring detection accuracy, communication
overhead, poisoning-attack detection/false-positive rates, and convergence
speed compared to centralized and standard federated baselines.

## Objectives

1. Design a Federated Learning framework capable of training an intrusion
   detection model across multiple distributed clients without centralizing
   raw network traffic data.
2. Design and implement a custom, security-fused communication protocol that
   combines lightweight message integrity verification and a cheap
   transport-layer anomaly "fingerprint" check with efficient exchange of
   model updates — filtering tampered or malicious updates before they reach
   the server's aggregation stage, rather than relying solely on post-hoc
   server-side robust aggregation.
3. Evaluate the system's intrusion detection performance (accuracy, precision,
   recall, F1-score) on benchmark datasets under a federated setting.
4. Analyse communication overhead, convergence behaviour, and scalability of
   the custom protocol against standard federated learning communication
   methods (e.g., gRPC/HTTP as baseline), including the added cost of the
   integrity/fingerprint layer itself.
5. Assess the system's robustness against client dropouts, non-IID data
   distribution across clients, and adversarial/malicious client updates —
   measuring the custom protocol's early detection rate and false-positive
   rate on injected label-flipping and backdoor poisoning attacks, and
   comparing outcomes with and without server-side aggregation defenses
   (e.g., Krum, trimmed mean) layered on top.

## Motivation

With the rapid growth of interconnected devices and network infrastructure,
cyberattacks have become more frequent, sophisticated, and distributed in
nature. Traditional centralized NIDS require aggregating traffic logs from
multiple network segments or organizations into one location for model
training — but this is often impractical or unsafe: network traffic can reveal
sensitive information about users, internal infrastructure, and business
operations, and many organizations are unwilling or legally unable (e.g., under
data protection regulations) to share this data externally.

Federated Learning addresses this privacy gap by keeping data local and only
sharing model parameters, making collaborative intrusion detection feasible
across organizational or geographic boundaries. However, standard federated
learning implementations often use generic, heavyweight communication
protocols not optimized for the specific needs of this setting — frequent
small updates, unreliable network links at the edge, and the need for
verifying update integrity to prevent poisoning attacks. This motivates the
design of a custom, purpose-built communication protocol that makes federated
NIDS both more practical for real-world, bandwidth-constrained deployments and
more secure against communication-level threats, ultimately contributing
toward a scalable, privacy-preserving approach to network security.

## Novelty / Research Gap

Federated Learning for NIDS is a well-established research area (see
`References` below for a comprehensive 2024 survey). Within it, two
sub-problems are usually solved **separately**:

- **Communication efficiency** — reducing the bandwidth cost of sending model
  updates, typically via compression, quantization, or smarter client
  selection (e.g., eFedAD, adaptive client selection). These approaches do
  not address security.
- **Robustness to malicious/poisoned updates** — typically handled entirely
  at the server, *after* an update has already been fully received and
  processed, via robust aggregation strategies (FedAvg variants, Krum,
  trimmed mean, median-based aggregation).

**This project fuses the two at the protocol level.** Rather than treating
bandwidth and security as independent concerns solved at different stages,
the custom protocol attaches a compact integrity tag and statistical
fingerprint to each update at the point of transmission, enabling a cheap,
early anomaly check *before* the expensive server-side aggregation pipeline
runs — reducing wasted bandwidth/compute on updates that are corrupted or
maliciously poisoned, while still allowing existing robust-aggregation
methods to run as a second line of defense on updates that pass. To the best
of our review, this specific combination — transport-layer integrity +
anomaly filtering, co-designed with (rather than bolted onto) an
efficiency-oriented FL communication protocol for NIDS — is not directly
addressed in existing literature, which is the gap this project targets.

## Model

- **Architecture:** Multi-Layer Perceptron (MLP) — feedforward neural network
  (input layer sized to the encoded feature count → hidden layer, 128 neurons,
  ReLU → hidden layer, 64 neurons, ReLU → output layer, 1 neuron, sigmoid).
- **Task:** Binary classification (`normal` vs `attack`) as the first
  milestone; multi-class attack-type classification as a later extension.
- **Why an MLP:** the dataset is tabular (rows of numeric/categorical
  connection features), not image or sequence data, so a simple feedforward
  network is the standard, well-supported choice for this task and averages
  cleanly under FedAvg.

## Dataset

- **NSL-KDD** — an improved version of the classic KDD Cup 99 intrusion
  detection benchmark, 41 features per network connection record + label.
- Source: [UNB Canadian Institute for Cybersecurity](https://www.unb.ca/cic/datasets/nsl.html)
  (official reference; direct download currently unavailable at time of
  writing). Files were obtained via the
  [jmnwong/NSL-KDD-Dataset](https://github.com/jmnwong/NSL-KDD-Dataset) GitHub
  mirror.
- Files used: `data/KDDTrain+.txt` (training set, ~125,973 rows),
  `data/KDDTest+.txt` (test set, ~22,544 rows).
- **CICIDS2017** planned as a second benchmark dataset for Objective 3 (not
  yet downloaded).

## Project Structure

```
fl-nids-project/
├── data/                   # Raw dataset files (not tracked in git)
│   ├── KDDTrain+.txt
│   └── KDDTest+.txt
├── venv/                   # Python virtual environment (not tracked in git)
├── requirements.txt        # Python dependencies
├── .gitignore
└── README.md                # This file
```

## Setup

```
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Progress Log

- **Phase 1 — Environment setup:** Done. Project folder created, virtual
  environment created, `requirements.txt` defined.
- **Phase 2 — Dataset acquisition:** Done. NSL-KDD train/test files downloaded
  into `data/`.
- **Phase 3 — Preprocessing:** Not started.
- **Phase 4 — Client simulation (data partitioning):** Not started.
- **Phase 5 — Model definition:** Not started.
- **Phase 6 — Federated training loop (FedAvg):** Not started.
- **Phase 7 — Evaluation:** Not started.
- **Custom communication protocol (Objective 2):** Direction finalized —
  security-fused protocol (integrity + anomaly fingerprinting at the
  transport layer). Implementation planned after the baseline federated
  pipeline (Phases 1–7) is working end to end.

## References

- Khraisat, A., Alazab, A., Singh, S., Jan, T., & Gomez, A. Jr. (2024).
  Survey on Federated Learning for Intrusion Detection System: Concept,
  Architectures, Aggregation Strategies, Challenges, and Future Directions.
  *ACM Computing Surveys, 57*(1), Article 7.
  https://doi.org/10.1145/3687124
- Communication-Efficient Federated Learning for Network Traffic Anomaly
  Detection (eFedAD). IEEE Conference Publication.
  https://ieeexplore.ieee.org/iel8/10566866/10566894/10566998.pdf
- Reducing Communication Overhead in Federated Learning for Network Anomaly
  Detection with Adaptive Client Selection (2025). arXiv:2503.15448.
  https://arxiv.org/pdf/2503.15448
