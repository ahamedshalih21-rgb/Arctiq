import React from 'react';

export default function ValueMetric({ value }) {
  if (!value) return null;

  const preserved = value.value_preserved_usd  ?? 0;
  const atRisk    = value.value_at_risk_usd    ?? 0;
  const total     = value.total_batch_value_usd ?? 0;
  const riskPct   = value.risk_factor_pct      ?? 0;

  return (
    <div className="value-card">
      <div className="value-section-title">Value Estimate</div>
      <div className="value-body">
        {/* Main metric */}
        <div className="value-main-row">
          <span className="value-main-num">
            ${preserved.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span className="value-main-label">preserved</span>
        </div>
        <div className="value-sub-label">estimated value protected from loss</div>

        {/* Breakdown table */}
        <div className="value-breakdown">
          <div className="value-row">
            <span className="vr-label">Batch Total</span>
            <span className="vr-value total">${total.toFixed(2)}</span>
          </div>
          <div className="value-row">
            <span className="vr-label">At Risk</span>
            <span className="vr-value at-risk">${atRisk.toFixed(2)} ({riskPct}%)</span>
          </div>
          <div className="value-row">
            <span className="vr-label">Preserved</span>
            <span className="vr-value preserved">${preserved.toFixed(2)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
