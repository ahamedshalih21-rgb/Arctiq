import React from 'react';

const RISK_ICONS = { Safe: '✅', Watch: '⚠️', Critical: '🚨' };
const RISK_LABELS = { Safe: 'SAFE', Watch: 'WATCH', Critical: 'CRITICAL' };

export default function RiskBadge({ prediction }) {
  const risk = prediction?.risk_level ?? 'Safe';
  const hours = prediction?.hours_remaining ?? '--';
  const confidence = prediction?.confidence ?? 0;

  return (
    <div className={`risk-card glass-card ${risk}`}>
      <div className={`risk-glow ${risk}`} />
      <div className="risk-label">Spoilage Risk Status</div>

      <div className={`risk-badge ${risk}`}>
        <span className="risk-icon">{RISK_ICONS[risk]}</span>
        {RISK_LABELS[risk]}
      </div>

      <div className={`hours-display ${risk}`}>
        {typeof hours === 'number' ? hours.toFixed(1) : '--'}
      </div>
      <div className="hours-sub">hours until spoilage risk</div>

      <div className="confidence-bar">
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
  );
}
