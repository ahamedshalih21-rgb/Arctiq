import React from 'react';

/**
 * CompressorHealth — Simplified
 * --------------------------------
 * Displays only the three required fields:
 *   Health Score | Status | Run Time
 *
 * Per UI requirements, all other compressor metrics (temperature, current,
 * duty cycle, Arrhenius factor, cumulative damage, start-stop cycles) have
 * been removed from this view. They remain available via /api/compressor.
 */

function statusClass(status) {
  if (!status)             return 'Safe';
  if (status === 'Healthy')  return 'Safe';
  if (status === 'Warning')  return 'Watch';
  if (status === 'Critical') return 'Critical';
  return 'Safe';
}

export default function CompressorHealth({ data }) {
  if (!data) {
    return (
      <div className="hmi-card">
        <div className="hmi-section-title">Compressor Health</div>
        <div className="bi-table">
          <div className="bi-row">
            <span className="bi-label">Status</span>
            <span className="bi-value" style={{ color: 'var(--color-neutral-600)' }}>Loading...</span>
          </div>
        </div>
      </div>
    );
  }

  const {
    health_score   = null,
    health_status  = '--',
    runtime_hours  = null,
    demo_mode      = false,
  } = data;

  const sc          = statusClass(health_status);
  const scoreColor  = sc === 'Safe' ? 'var(--risk-safe)' : sc === 'Watch' ? 'var(--risk-watch)' : 'var(--risk-critical)';

  return (
    <div className="hmi-card">
      <div className="hmi-section-title">Compressor Health</div>

      <div className="bi-table">

        <div className="bi-row">
          <span className="bi-label">Health Score</span>
          <span className="bi-value">
            <span style={{ color: scoreColor }}>
              {health_score !== null ? health_score.toFixed(1) : '--'}
            </span>
            <span style={{ color: 'var(--color-neutral-600)', fontWeight: 400, marginLeft: 2 }}> / 100</span>
          </span>
        </div>

        <div className="bi-row">
          <span className="bi-label">Status</span>
          <span>
            <span
              className={`risk-badge ${sc}`}
              style={{ fontSize: '0.62rem', padding: '1px 6px' }}
            >
              <span className="risk-dot" />
              {health_status.toUpperCase()}
            </span>
          </span>
        </div>

        <div className="bi-row" style={{ borderBottom: 'none' }}>
          <span className="bi-label">Run Time</span>
          <span className="bi-value">
            {runtime_hours !== null ? runtime_hours.toFixed(1) : '--'}
            <span style={{ color: 'var(--color-neutral-600)', fontWeight: 400 }}> h</span>
          </span>
        </div>

      </div>

      {demo_mode && (
        <div
          style={{
            padding: 'var(--space-3) var(--space-6)',
            borderTop: '1px solid var(--color-divider)',
            fontSize: '0.58rem',
            color: 'var(--color-neutral-600)',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          Demo Mode — Accelerated Degradation
        </div>
      )}
    </div>
  );
}
