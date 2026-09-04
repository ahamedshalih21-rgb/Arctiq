import React from 'react';

/**
 * RiskBadge — Two-Stage Warning Display
 * ----------------------------------------
 * Shows both the model-driven operational reference and the trend-based
 * projected risk horizon, clearly labeled to avoid misrepresentation.
 *
 * Labels:
 *   "Model Prediction" = GBR model's hours_remaining output (operational reference)
 *   "Projected Horizon" = trend-based early warning estimate (not model-validated)
 */

const STAGE_LABELS = {
  LOW:           'LOW RISK',
  MEDIUM:        'MEDIUM RISK',
  HIGH:          'HIGH RISK',
  SAFE:          'SAFE',
  MONITOR:       'MONITOR',
  WATCH:         'WATCH',
  EARLY_WARNING: 'EARLY WARNING',
  HIGH_RISK:     'HIGH RISK',
  CRITICAL:      'CRITICAL',
  SPOILED:       'SPOILED',
};

const STAGE_CSS_CLASS = {
  LOW:           'Safe',
  MEDIUM:        'Watch',
  HIGH:          'HighRisk',
  Safe:          'Safe',
  Watch:         'Watch',
  Critical:      'Critical',
  SAFE:          'Safe',
  MONITOR:       'Safe',
  WATCH:         'Watch',
  EARLY_WARNING: 'Watch',
  HIGH_RISK:     'HighRisk',
  CRITICAL:      'Critical',
  SPOILED:       'Critical',
};

export default function RiskBadge({ prediction }) {
  const riskLevel     = prediction?.risk_level       ?? 'Safe';
  const hours         = prediction?.hours_remaining   ?? null;
  const confidence    = prediction?.confidence        ?? 0;
  const warningStage  = prediction?.warning_stage     ?? null;
  const projected     = prediction?.projected_risk_horizon_hours ?? null;
  const modelHours    = prediction?.model_hours_remaining ?? hours;
  const earlyWarning  = prediction?.early_warning_active   ?? false;
  const criticalActive = prediction?.critical_action_active ?? false;
  const description   = prediction?.warning_description   ?? '';

  // Determine display classes
  const stageCss   = warningStage ? STAGE_CSS_CLASS[warningStage] : riskLevel;
  const stageLabel = warningStage ? STAGE_LABELS[warningStage] : riskLevel.toUpperCase();

  // Color mapping
  const stageColor = {
    SAFE:          'var(--risk-safe)',
    MONITOR:       'var(--risk-safe)',
    WATCH:         'var(--risk-watch)',
    EARLY_WARNING: 'var(--risk-watch)',
    HIGH_RISK:     'var(--risk-high)',
    CRITICAL:      'var(--risk-critical)',
    SPOILED:       'var(--color-neutral-600)',
  }[warningStage] || 'var(--color-neutral-400)';

  return (
    <div className="risk-card">
      {/* Header */}
      <div className="risk-header">
        <div className="risk-header-title">Spoilage Risk</div>
        <div
          className={`risk-badge ${stageCss}`}
          style={
            stageCss === 'HighRisk'
              ? { color: 'var(--risk-high)', borderColor: 'var(--risk-high)', background: 'var(--risk-high-bg)' }
              : {}
          }
        >
          <div className="risk-dot" />
          {stageLabel}
        </div>
      </div>

      <div className="risk-body">
        {/* Two-stage panel */}
        <div className="risk-two-stage">

          {/* Stage 2: Model prediction (primary / high-confidence reference) */}
          <div className="risk-stage-block">
            <div className="hmi-label" style={{ marginBottom: 4 }}>Model Prediction</div>
            <div className="risk-hours-row">
              <span className={`risk-hours-val ${riskLevel}`}>
                {modelHours != null ? modelHours.toFixed(1) : '--'}
              </span>
              <span className="risk-hours-unit">hrs</span>
            </div>
            <div className="risk-stage-desc">
              {criticalActive
                ? 'Critical action window — model-driven reference'
                : 'Model-driven operational reference'}
            </div>
          </div>

          <div className="risk-stage-divider" />

          {/* Stage 1: Projected horizon (trend-based early warning) */}
          <div className="risk-stage-block">
            <div className="hmi-label" style={{ marginBottom: 4, color: earlyWarning ? 'var(--risk-watch)' : undefined }}>
              Projected Horizon
            </div>
            <div className="risk-hours-row">
              <span
                className="risk-hours-val"
                style={{ color: projected != null && projected <= 12 ? 'var(--risk-watch)' : 'var(--color-neutral-400)' }}
              >
                {projected != null ? `~${Math.round(projected)}` : '--'}
              </span>
              <span className="risk-hours-unit">hrs</span>
            </div>
            <div className="risk-stage-desc">
              Trend-based early warning estimate
            </div>
          </div>

        </div>

        {/* Warning description */}
        {description && (
          <div className="risk-description">{description}</div>
        )}

        {/* Confidence bar */}
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
