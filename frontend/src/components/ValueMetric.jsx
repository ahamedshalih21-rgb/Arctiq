import React from 'react';

export default function ValueMetric({ value }) {
  if (!value) return null;

  const preserved = value.value_preserved_usd ?? 0;
  const atRisk = value.value_at_risk_usd ?? 0;
  const total = value.total_batch_value_usd ?? 0;
  const riskPct = value.risk_factor_pct ?? 0;

  return (
    <div className="value-card glass-card">
      <div className="value-title">💰 Estimated Value Preserved</div>

      <div className="value-main">${preserved.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
      <div className="value-sub-label">protected from loss with early detection</div>

      <div className="value-breakdown">
        <div className="value-row">
          <span className="vr-label">Total Batch Value</span>
          <span className="vr-value total">${total.toFixed(2)}</span>
        </div>
        <div className="value-row">
          <span className="vr-label">Value at Risk</span>
          <span className="vr-value at-risk">${atRisk.toFixed(2)} ({riskPct}%)</span>
        </div>
        <div className="value-row">
          <span className="vr-label">Preserved</span>
          <span className="vr-value preserved">${preserved.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
