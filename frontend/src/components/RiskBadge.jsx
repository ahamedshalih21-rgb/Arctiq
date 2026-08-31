import React from 'react';

export default function RiskBadge({ prediction }) {
  const risk    = prediction?.risk_level  ?? 'Safe';
  const hours   = prediction?.hours_remaining ?? null;
  const confidence = prediction?.confidence ?? 0;

  return (
    <div className="risk-card">
      {/* Header row — label + compact badge side by side */}
      <div className="risk-header">
        <div className="risk-header-title">Spoilage Risk</div>
        <div className={`risk-badge ${risk}`}>
          <div className="risk-dot" />
          {risk.toUpperCase()}
        </div>
      </div>

      {/* Body — hours countdown + confidence bar */}
      <div className="risk-body">
        <div>
          <div className="hmi-label" style={{ marginBottom: '6px' }}>Hours Until Risk</div>
          <div className="risk-hours-row">
            <span className={`risk-hours-val ${risk}`}>
              {hours !== null ? hours.toFixed(1) : '--'}
            </span>
            <span className="risk-hours-unit">hrs</span>
          </div>
        </div>

        <div className="confidence-section">
          <div className="confidence-label-row">
            <span>Model Confidence</span>
            <span>{Math.round(confidence * 100)}%</span>
          </div>
          <div className="confidence-track">
            <div
              className="confidence-fill"
              style={{ width: `${Math.round(confidence * 100)}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
