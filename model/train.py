"""
Arctiq — PyTorch LSTM Spoilage Prediction Model Training
===========================================================
Architecture:
  - Input: 360 timesteps (6 hours at 1-minute resolution) x 10 features
  - Backbone: 2-layer LSTM (hidden_dim=64, dropout=0.20)
  - Head: Fully Connected MLP (64 -> 32 -> ReLU -> 16 -> ReLU -> 1)
  - Target: remaining_shelf_life_hours (continuous regression)

Risk Classification Layer (Deterministic):
  - > 24 hours    -> LOW RISK
  - 12–24 hours   -> MEDIUM RISK
  - <= 12 hours   -> HIGH RISK (12-hour intervention window)

Saves:
  - model/saved_model/arctiq_lstm.pt (PyTorch state dict & model spec)
  - model/saved_model/scaler.joblib (Fitted StandardScaler for 10 features)
  - model/saved_model/metrics.json (Evaluation performance)
  - model/plots/loss_curve.png, sample_predictions.png
"""

import os
import sys
import json
import random
import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, classification_report

# ── Reproducibility ────────────────────────────────────────────────────────────
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

SCRIPT_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
MODEL_DIR = os.path.join(SCRIPT_DIR, "saved_model")
PLOT_DIR = os.path.join(SCRIPT_DIR, "plots")
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)

WINDOW_SIZE = 360
NUM_FEATURES = 10
BATCH_SIZE = 64
EPOCHS = 35
LEARNING_RATE = 1e-3

# ── Spoilage Risk Thresholds (Operational Intervention Window) ────────────────
def hours_to_risk(hours: float) -> str:
    """Deterministic 3-tier risk layer."""
    if hours > 24.0:
        return "LOW"
    elif hours > 12.0:
        return "MEDIUM"
    return "HIGH"


# ── PyTorch LSTM Architecture ─────────────────────────────────────────────────
class ArctiqLSTM(nn.Module):
    def __init__(self, input_dim: int = 10, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        
        self.fc_block = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        # x shape: (batch_size, 360, 10)
        lstm_out, _ = self.lstm(x)
        # Take the hidden state of the final timestep (360)
        last_timestep = lstm_out[:, -1, :]
        out = self.fc_block(last_timestep)
        return out.squeeze(-1)


# ── Data Loading & Standardization ────────────────────────────────────────────
def load_and_preprocess_data():
    train_path = os.path.join(DATA_DIR, "train_sequences.npz")
    test_path = os.path.join(DATA_DIR, "test_sequences.npz")
    
    if not os.path.exists(train_path) or not os.path.exists(test_path):
        raise FileNotFoundError(
            f"Sequence files not found in {DATA_DIR}. Please run data_generator/generate.py first!"
        )

    print("Loading pre-extracted sequence datasets...")
    train_npz = np.load(train_path)
    test_npz = np.load(test_path)

    X_train = train_npz["X"]  # (N_train, 360, 10)
    y_train = train_npz["y"]  # (N_train,)
    feature_names = train_npz["feature_names"]

    X_test = test_npz["X"]    # (N_test, 360, 10)
    y_test = test_npz["y"]    # (N_test,)

    print(f"  Train: X={X_train.shape}, y={y_train.shape}")
    print(f"  Test:  X={X_test.shape},  y={y_test.shape}")
    print(f"  Features ({len(feature_names)}): {list(feature_names)}")

    # Fit StandardScaler on 2D reshaped training features across all timesteps
    N_tr, T, F = X_train.shape
    N_te, _, _ = X_test.shape

    scaler = StandardScaler()
    X_train_flat = X_train.reshape(-1, F)
    scaler.fit(X_train_flat)

    X_train_scaled = scaler.transform(X_train_flat).reshape(N_tr, T, F).astype(np.float32)
    X_test_scaled = scaler.transform(X_test.reshape(-1, F)).reshape(N_te, T, F).astype(np.float32)

    # Save scaler for backend inference
    scaler_path = os.path.join(MODEL_DIR, "scaler.joblib")
    joblib.dump(scaler, scaler_path)
    print(f"StandardScaler saved to: {scaler_path}")

    # Also save scaling parameters as JSON for inspection
    scaler_json_path = os.path.join(MODEL_DIR, "scaler_params.json")
    with open(scaler_json_path, "w") as f:
        json.dump({
            "features": [str(f) for f in feature_names],
            "means": scaler.mean_.tolist(),
            "scales": scaler.scale_.tolist(),
        }, f, indent=2)

    return X_train_scaled, y_train, X_test_scaled, y_test, feature_names


# ── Training Loop ─────────────────────────────────────────────────────────────
def train_arctiq_lstm():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nUsing compute device: {device}")

    X_train, y_train, X_test, y_test, feature_names = load_and_preprocess_data()

    train_dataset = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    test_dataset = TensorDataset(torch.from_numpy(X_test), torch.from_numpy(y_test))

    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

    model = ArctiqLSTM(input_dim=NUM_FEATURES, hidden_dim=64, num_layers=2, dropout=0.2).to(device)
    print("\nModel Architecture:")
    print(model)

    criterion = nn.HuberLoss(delta=1.0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)

    history = {"train_loss": [], "val_loss": [], "val_mae": []}
    best_val_loss = float("inf")
    best_weights = None
    patience = 8
    patience_counter = 0

    print(f"\nStarting training for {EPOCHS} epochs...")
    print(f"{'Epoch':>6} | {'Train Loss':>12} | {'Val Loss':>12} | {'Val MAE (h)':>12}")
    print("-" * 52)

    for epoch in range(1, EPOCHS + 1):
        # 1. Training
        model.train()
        train_loss = 0.0
        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(device), batch_y.to(device)
            optimizer.zero_grad()
            preds = model(batch_X)
            loss = criterion(preds, batch_y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item() * len(batch_y)

        train_loss /= len(train_dataset)

        # 2. Validation
        model.eval()
        val_loss = 0.0
        val_abs_err = 0.0
        with torch.no_grad():
            for batch_X, batch_y in test_loader:
                batch_X, batch_y = batch_X.to(device), batch_y.to(device)
                preds = model(batch_X)
                loss = criterion(preds, batch_y)
                val_loss += loss.item() * len(batch_y)
                val_abs_err += torch.sum(torch.abs(preds - batch_y)).item()

        val_loss /= len(test_dataset)
        val_mae = val_abs_err / len(test_dataset)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_mae"].append(val_mae)

        scheduler.step(val_loss)

        print(f"{epoch:>6d} | {train_loss:>12.4f} | {val_loss:>12.4f} | {val_mae:>12.2f}")

        # Checkpointing
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = model.state_dict().copy()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"\nEarly stopping triggered at epoch {epoch}.")
                break

    # Restore best weights
    if best_weights is not None:
        model.load_state_dict(best_weights)

    # ── Evaluation & Metrics ──────────────────────────────────────────────────
    model.eval()
    all_preds = []
    with torch.no_grad():
        for batch_X, _ in test_loader:
            batch_X = batch_X.to(device)
            preds = model(batch_X)
            all_preds.append(preds.cpu().numpy())

    y_pred = np.concatenate(all_preds)

    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = float(r2_score(y_test, y_pred))

    print("\n" + "=" * 52)
    print("Test Set Regression Evaluation:")
    print(f"  MAE:  {mae:.2f} hours")
    print(f"  RMSE: {rmse:.2f} hours")
    print(f"  R2:   {r2:.4f}")
    print("=" * 52)

    # Risk classification performance
    risk_true = [hours_to_risk(h) for h in y_test]
    risk_pred = [hours_to_risk(h) for h in y_pred]
    risk_report = classification_report(risk_true, risk_pred, output_dict=True)
    print("\nRisk Classification Performance (>24h LOW, 12-24h MEDIUM, <=12h HIGH):")
    print(classification_report(risk_true, risk_pred))

    # Save Model Weights & Metadata
    model_save_path = os.path.join(MODEL_DIR, "arctiq_lstm.pt")
    torch.save({
        "model_state_dict": model.state_dict(),
        "input_dim": NUM_FEATURES,
        "hidden_dim": 64,
        "num_layers": 2,
        "features": [str(f) for f in feature_names],
        "metrics": {"mae": mae, "rmse": rmse, "r2": r2},
        "thresholds": {"low_above": 24.0, "medium_above": 12.0},
    }, model_save_path)
    print(f"\nModel checkpoint saved: {model_save_path}")

    # Save metrics JSON
    metrics_path = os.path.join(MODEL_DIR, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump({
            "model_type": "PyTorch_LSTM",
            "mae_hours": round(mae, 3),
            "rmse_hours": round(rmse, 3),
            "r2_score": round(r2, 4),
            "epochs_trained": len(history["train_loss"]),
            "risk_classification": risk_report,
        }, f, indent=2)
    print(f"Metrics JSON saved: {metrics_path}")

    # Plot Loss Curve
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(history["train_loss"], label="Train Huber Loss", color="#4ECDC4", linewidth=2)
    ax.plot(history["val_loss"], label="Val Huber Loss", color="#FF6B6B", linewidth=2, linestyle="--")
    ax.set_xlabel("Epoch", fontsize=12)
    ax.set_ylabel("Loss", fontsize=12)
    ax.set_title("Arctiq LSTM — Training & Validation Loss", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    loss_fig_path = os.path.join(PLOT_DIR, "loss_curve.png")
    fig.savefig(loss_fig_path, dpi=150)
    plt.close()
    print(f"Loss plot saved: {loss_fig_path}")

    # Plot Predictions
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    ax = axes[0]
    ax.scatter(y_test, y_pred, alpha=0.35, color="#4ECDC4", s=15)
    mn, mx = min(y_test.min(), y_pred.min()), max(y_test.max(), y_pred.max())
    ax.plot([mn, mx], [mn, mx], "r--", linewidth=1.5, label="Perfect 1:1")
    ax.set_xlabel("Actual Remaining Shelf Life (hours)", fontsize=11)
    ax.set_ylabel("Predicted Remaining Shelf Life (hours)", fontsize=11)
    ax.set_title(f"Predicted vs Actual (Test Batches) — R² = {r2:.3f}", fontsize=13, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    errors = y_pred - y_test
    ax.hist(errors, bins=40, color="#6C63FF", alpha=0.8, edgecolor="white", linewidth=0.4)
    ax.axvline(0, color="red", linestyle="--", linewidth=1.5)
    ax.set_xlabel("Prediction Error (hours)", fontsize=11)
    ax.set_ylabel("Sample Count", fontsize=11)
    ax.set_title(f"Error Distribution (MAE = {mae:.2f}h)", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    pred_fig_path = os.path.join(PLOT_DIR, "sample_predictions.png")
    fig.savefig(pred_fig_path, dpi=150)
    plt.close()
    print(f"Prediction scatter plot saved: {pred_fig_path}")

    # Sample output
    print("\nSample Predictions on Unseen Test Batches:")
    print(f"{'Actual (h)':>12} | {'Predicted (h)':>14} | {'Risk (Actual)':>14} | {'Risk (Predicted)':>16}")
    print("-" * 62)
    indices = np.linspace(0, len(y_test) - 1, 10, dtype=int)
    for idx in indices:
        act, prd = y_test[idx], y_pred[idx]
        print(f"{act:>12.1f} | {prd:>14.1f} | {hours_to_risk(act):>14} | {hours_to_risk(prd):>16}")

    return model


if __name__ == "__main__":
    train_arctiq_lstm()
