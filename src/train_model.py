"""
Step 1 of 3 - TRAINING (70 / 15 / 15 split).

Trains the models on the 70% training set. The 15% validation set is used
for early stopping and to choose the decision threshold. The test set is
NOT touched here. Each trained model is saved to
results/split_701515/models/ for src/test_model.py.

Run: venv\\Scripts\\python.exe src\\train_model.py [centralized] [router] [iid]
     (no arguments = all three models)
"""

import sys

from split_experiment import SETS, load, parts_from_args, save_model, train_one


def main():
    names = parts_from_args(sys.argv[1:])
    d = load()
    print("Flows per set:", {s: len(d[f"y_{s}"]) for s in SETS})
    for name in names:
        model, info = train_one(d, name)
        save_model(name, model, info)
    print("\nTraining done. Next: venv\\Scripts\\python.exe src\\test_model.py")


if __name__ == "__main__":
    main()
