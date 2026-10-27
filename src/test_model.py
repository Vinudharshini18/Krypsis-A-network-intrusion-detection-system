"""
Step 2 of 3 - TESTING (70 / 15 / 15 split).

Loads the models saved by src/train_model.py and evaluates each one on the
train, validation and test sets (and the extra TEST capture), with the
threshold chosen on validation during training. Saves the numbers to
results/split_701515/<model>.json.

Run: venv\\Scripts\\python.exe src\\test_model.py [centralized] [router] [iid]
     (no arguments = all three models)
"""

import sys

from split_experiment import load, load_model, parts_from_args, test_one


def main():
    names = parts_from_args(sys.argv[1:])
    d = load()
    for name in names:
        model, info = load_model(name)
        test_one(d, name, model, info)
    print("\nTesting done. Next: venv\\Scripts\\python.exe src\\show_results.py")


if __name__ == "__main__":
    main()
