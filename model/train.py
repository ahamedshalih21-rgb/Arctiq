"""
ColdSense — LSTM Training Script
Trains an LSTM regression model on the synthetic dataset.
Saves: model/saved_model/coldsense_model.keras
Plots: model/plots/loss_curve.png, sample_predictions.png
"""

import numpy as np
import pandas as pd
import os
import sys
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(SCRIPT_DIR, "data", "training_data.csv")
MODEL_DIR = os.path.join(SCRIPT_DIR, "saved_model")
PLOT_DIR = os.path.join(SCRIPT_DIR, "plots")
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)

WINDOW = 24
FEATURES = ["temperature", "humidity", "door_open_event", "produce_type"]
LABEL = "hours_until_spoilage"
EPOCHS = 40
BATCH_SIZE = 64
VALIDATION_SPLIT = 0.15
SEED = 42

# Risk thresholds (hours)
SAFE_THRESHOLD = 48.0
WATCH_THRESHOLD = 24.0


def hours_to_risk(hours: float) -> str:
    if hours > SAFE_THRESHOLD:
        return "Safe"
    elif hours > WATCH_THRESHOLD:
        return "Watch"
    return "Critical"


def load_and_reshape(data_path: str):
    """Load CSV → reshape into (N, 24, 4) numpy arrays."""
    print("Loading data...")
    df = pd.read_csv(data_path)
    print(f"  Loaded {len(df)} rows, {df['seq_id'].nunique()} sequences")

    # Normalize features
    temp_mean, temp_std = df["temperature"].mean(), df["temperature"].std()
    hum_mean, hum_std = df["humidity"].mean(), df["humidity"].std()

    df["temperature"] = (df["temperature"] - temp_mean) / temp_std
    df["humidity"] = (df["humidity"] - hum_mean) / hum_std
    # door_open_event is already 0/1
    # produce_type already 0/1/2 — normalize to [0,1]
    df["produce_type"] = df["produce_type"] / 2.0

    # Normalize label (will de-normalize for eval)
    label_mean = df.groupby("seq_id")[LABEL].first().mean()
    label_std = df.groupby("seq_id")[LABEL].first().std()

    # Build sequences
    seqs = df.groupby("seq_id", sort=False)
    X_list, y_list = [], []
    for seq_id, group in seqs:
        group = group.sort_values("timestep")
        if len(group) != WINDOW:
            continue
        X_list.append(group[FEATURES].values)
        y_list.append(group[LABEL].iloc[-1])

    X = np.array(X_list, dtype=np.float32)   # (N, 24, 4)
    y_raw = np.array(y_list, dtype=np.float32)
    y = (y_raw - label_mean) / label_std      # normalized labels

    norm_params = {
        "temp_mean": float(temp_mean), "temp_std": float(temp_std),
        "hum_mean": float(hum_mean), "hum_std": float(hum_std),
        "label_mean": float(label_mean), "label_std": float(label_std),
    }

    print(f"  X shape: {X.shape}, y shape: {y.shape}")
    return X, y, y_raw, norm_params


def build_lstm_model(input_shape):
    """Build LSTM regression model. Falls back to GBR if TF unavailable."""
    try:
        import tensorflow as tf
        tf.random.set_seed(SEED)

        inputs = tf.keras.Input(shape=input_shape)
        x = tf.keras.layers.LSTM(64, return_sequences=True)(inputs)
        x = tf.keras.layers.Dropout(0.2)(x)
        x = tf.keras.layers.LSTM(32)(x)
        x = tf.keras.layers.Dropout(0.15)(x)
        x = tf.keras.layers.Dense(32, activation="relu")(x)
        x = tf.keras.layers.Dense(16, activation="relu")(x)
        outputs = tf.keras.layers.Dense(1)(x)

        model = tf.keras.Model(inputs, outputs)
        model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="mse", metrics=["mae"])
        return model, "lstm"

    except ImportError:
        print("  TensorFlow not available — using GradientBoostingRegressor fallback")
        return None, "gbr"


def train_lstm(X, y, y_raw, norm_params):
    import tensorflow as tf
    np.random.seed(SEED)
    tf.random.set_seed(SEED)

    # Shuffle
    idx = np.random.permutation(len(X))
    X, y, y_raw = X[idx], y[idx], y_raw[idx]

    split = int(len(X) * (1 - VALIDATION_SPLIT))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]
    y_raw_val = y_raw[split:]

    model, model_type = build_lstm_model((WINDOW, X.shape[2]))

    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=6, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3),
    ]

    print("\nTraining LSTM...")
    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=callbacks,
        verbose=1,
    )

    # Save model
    model_path = os.path.join(MODEL_DIR, "coldsense_model.keras")
    model.save(model_path)
    print(f"\nModel saved: {model_path}")

    # Save norm params
    norm_path = os.path.join(MODEL_DIR, "norm_params.json")
    with open(norm_path, "w") as f:
        json.dump(norm_params, f, indent=2)
    print(f"Norm params saved: {norm_path}")

    # Evaluation
    y_pred_norm = model.predict(X_val, verbose=0).flatten()
    y_pred = y_pred_norm * norm_params["label_std"] + norm_params["label_mean"]

    return history, y_raw_val, y_pred, model_type


def train_gbr(X, y_raw, norm_params):
    """Fallback: GradientBoostingRegressor on flattened sequences."""
    from sklearn.ensemble import GradientBoostingRegressor
    import joblib

    print("\nTraining GradientBoostingRegressor fallback...")
    X_flat = X.reshape(len(X), -1)

    idx = np.random.permutation(len(X_flat))
    X_flat, y_raw = X_flat[idx], y_raw[idx]
    split = int(len(X_flat) * (1 - VALIDATION_SPLIT))

    X_train, X_val = X_flat[:split], X_flat[split:]
    y_train, y_val = y_raw[:split], y_raw[split:]

    gbr = GradientBoostingRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.08,
        subsample=0.8, random_state=SEED, verbose=1
    )
    gbr.fit(X_train, y_train)

    model_path = os.path.join(MODEL_DIR, "coldsense_model.joblib")
    joblib.dump(gbr, model_path)
    norm_path = os.path.join(MODEL_DIR, "norm_params.json")
    with open(norm_path, "w") as f:
        json.dump({**norm_params, "model_type": "gbr"}, f, indent=2)
    print(f"GBR model saved: {model_path}")

    y_pred = gbr.predict(X_val)
    return None, y_val, y_pred, "gbr"


def plot_loss_curve(history):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(history.history["loss"], label="Train Loss", color="#4ECDC4", linewidth=2)
    ax.plot(history.history["val_loss"], label="Val Loss", color="#FF6B6B", linewidth=2, linestyle="--")
    ax.set_xlabel("Epoch", fontsize=12)
    ax.set_ylabel("MSE Loss", fontsize=12)
    ax.set_title("ColdSense LSTM — Training Loss Curve", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(PLOT_DIR, "loss_curve.png")
    fig.savefig(path, dpi=150)
    print(f"Loss curve saved: {path}")
    plt.close()


def plot_predictions(y_true, y_pred):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Scatter
    ax = axes[0]
    ax.scatter(y_true, y_pred, alpha=0.4, color="#4ECDC4", s=15)
    mn, mx = min(y_true.min(), y_pred.min()), max(y_true.max(), y_pred.max())
    ax.plot([mn, mx], [mn, mx], "r--", linewidth=1.5, label="Perfect prediction")
    ax.set_xlabel("Actual hours_until_spoilage", fontsize=11)
    ax.set_ylabel("Predicted hours_until_spoilage", fontsize=11)
    ax.set_title("Predicted vs Actual (Validation Set)", fontsize=13, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Error distribution
    ax = axes[1]
    errors = y_pred - y_true
    ax.hist(errors, bins=50, color="#6C63FF", alpha=0.8, edgecolor="white", linewidth=0.3)
    ax.axvline(0, color="red", linestyle="--", linewidth=1.5)
    ax.set_xlabel("Prediction Error (hours)", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("Error Distribution", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    path = os.path.join(PLOT_DIR, "sample_predictions.png")
    fig.savefig(path, dpi=150)
    print(f"Predictions plot saved: {path}")
    plt.close()

    # Print sample predictions
    print("\nSample predictions (first 10 validation samples):")
    print(f"{'Actual':>10}  {'Predicted':>10}  {'Risk (actual)':>14}  {'Risk (pred)':>12}")
    print("-" * 52)
    for i in range(min(10, len(y_true))):
        print(f"{y_true[i]:>10.1f}  {y_pred[i]:>10.1f}  {hours_to_risk(y_true[i]):>14}  {hours_to_risk(y_pred[i]):>12}")

    mae = np.mean(np.abs(errors))
    print(f"\nValidation MAE: {mae:.2f} hours")


def main():
    print("ColdSense Model Trainer")
    print("=" * 40)

    if not os.path.exists(DATA_PATH):
        print(f"ERROR: Training data not found at {DATA_PATH}")
        print("Run data_generator/generate.py first.")
        sys.exit(1)

    X, y, y_raw, norm_params = load_and_reshape(DATA_PATH)

    # Try LSTM first, fall back to GBR
    try:
        import tensorflow as tf
        history, y_true, y_pred, model_type = train_lstm(X, y, y_raw, norm_params)
        if history:
            plot_loss_curve(history)
    except Exception as e:
        print(f"LSTM training failed ({e}), falling back to GBR...")
        history, y_true, y_pred, model_type = train_gbr(X, y_raw, norm_params)

    plot_predictions(y_true, y_pred)

    # Write model_type to norm_params for backend to read
    norm_params["model_type"] = model_type
    with open(os.path.join(MODEL_DIR, "norm_params.json"), "w") as f:
        json.dump(norm_params, f, indent=2)

    print(f"\n{'='*40}")
    print(f"Training complete! Model type: {model_type.upper()}")
    print(f"Model saved in: {os.path.abspath(MODEL_DIR)}")


if __name__ == "__main__":
    main()
