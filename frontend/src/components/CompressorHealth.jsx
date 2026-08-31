import React from 'react';

/**
 * CompressorHealth
 * ----------------
 * Displays compressor health data derived from the simulation-based
 * Arrhenius degradation model. Matches existing HMI card style.
 *
 * Layout: reuses .hmi-card, .bi-row, .bi-label, .bi-value, .risk-badge CSS.
 * No new visual language introduced.
 */

function statusClass(status) {
  if (!status) return 'Safe';
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
    health_score          = null,
    health_status         = '--',
    compressor_temperature = null,
    compressor_current    = null,
    duty_cycle            = null,
    arrhenius_stress_factor = null,
    cumulative_damage     = null,
    runtime_hours         = null,
    start_stop_cycles     = null,
    demo_mode             = false,
  } = data;

  const sc = statusClass(health_status);

  return (
    <div className="hmi-card">
      <div className="hmi-section-title">Compressor Health</div>

      <div className="bi-table">

        {/* Health Score + Status */}
        <div className="bi-row">
          <span className="bi-label">Health Score</span>
          <span className="bi-value">
            <span style={{ color: sc === 'Safe' ? 'var(--risk-safe)' : sc === 'Watch' ? 'var(--risk-watch)' : 'var(--risk-critical)' }}>
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

        {/* Temperature */}
        <div className="bi-row">
          <span className="bi-label">Comp. Temp</span>
          <span className="bi-value">
            {compressor_temperature !== null ? compressor_temperature.toFixed(1) : '--'}
            <span style={{ color: 'var(--color-neutral-600)', fontWeight: 400 }}> °C</span>
          </span>
        </div>

        {/* Current */}
        <div className="bi-row">
          <span className="bi-label">Current</span>
          <span className="bi-value">
            {compressor_current !== null ? compressor_current.toFixed(2) : '--'}
            <span style={{ color: 'var(--color-neutral-600)', fontWeight: 400 }}> A</span>
          </span>
        </div>

        {/* Duty Cycle */}
        <div className="bi-row">
          <span className="bi-label">Duty Cycle</span>
          <span className="bi-value">
            {duty_cycle !== null ? duty_cycle.toFixed(1) : '--'}
            <span style={{ color: 'var(--color-neutral-600)', fontWeight: 400 }}> %</span>
          </span>
        </div>

        {/* Arrhenius Stress Factor */}
        <div className="bi-row">
          <span className="bi-label">Arrhenius Factor</span>
          <span className="bi-value">
            {arrhenius_stress_factor !== null ? arrhenius_stress_factor.toFixed(4) : '--'}
          </span>
        </div>

        {/* Cumulative Damage */}
        <div className="bi-row">
          <span className="bi-label">Cum. Damage</span>
          <span className="bi-value">
            {cumulative_damage !== null ? (cumulative_damage * 100).toFixed(3) : '--'}
            <span style={{ color: 'var(--color-neutral-600)', fontWeight: 400 }}> %</span>
          </span>
        </div>

        {/* Runtime */}
        <div className="bi-row">
          <span className="bi-label">Runtime</span>
          <span className="bi-value">
            {runtime_hours !== null ? runtime_hours.toFixed(2) : '--'}
            <span style={{ color: 'var(--color-neutral-600)', fontWeight: 400 }}> h</span>
          </span>
        </div>

        {/* Start-Stop Cycles */}
        <div className="bi-row" style={{ borderBottom: 'none' }}>
          <span className="bi-label">Start-Stop Cycles</span>
          <span className="bi-value">
            {start_stop_cycles !== null ? start_stop_cycles : '--'}
          </span>
        </div>

      </div>

      {/* Demo mode indicator */}
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
