import React from 'react';

/**
 * CompressorHealth — Full Width Industrial Section
 * --------------------------------------------------
 * Arrhenius Degradation Model & Predictive Maintenance:
 *   - Health Gauge (0–100) with dynamic arc
 *   - Arrhenius Thermal Degradation Trend & Multiplier
 *   - Estimated Remaining Operating Life (Hours & Years)
 *   - Maintenance Alert Threshold Meter (75% Watch, 50% Critical)
 *   - Live Operating Diagnostics (Temp, Current, Cycles, Damage)
 */

function getHealthColor(score) {
  if (score >= 80) return 'var(--risk-safe)';
  if (score >= 60) return 'var(--risk-watch)';
  if (score >= 40) return 'var(--risk-high)';
  return 'var(--risk-critical)';
}

function getStatusBadge(status, score) {
  if (score >= 80 || status === 'Healthy') return { label: 'HEALTHY / OPTIMAL', cls: 'safe' };
  if (score >= 50 || status === 'Warning') return { label: 'MAINTENANCE WATCH', cls: 'watch' };
  return { label: 'CRITICAL ALERT', cls: 'critical' };
}

export default function CompressorHealth({ data }) {
  const d = data || {};
  const score = d.health_score != null ? Number(d.health_score) : 96.4;
  const status = d.health_status || 'Healthy';
  const runtimeHours = d.runtime_hours != null ? Number(d.runtime_hours) : 124.5;
  const compTemp = d.compressor_temperature != null ? Number(d.compressor_temperature) : 48.2;
  const compCurrent = d.compressor_current != null ? Number(d.compressor_current) : 5.4;
  const dutyCycle = d.duty_cycle != null ? Number(d.duty_cycle) : 54.8;
  const stressFactor = d.arrhenius_stress_factor != null ? Number(d.arrhenius_stress_factor) : 1.024;
  const cumulativeDamage = d.cumulative_damage != null ? Number(d.cumulative_damage) : 0.036;
  const cycles = d.start_stop_cycles != null ? Number(d.start_stop_cycles) : 18;
  const demoMode = d.demo_mode ?? true;

  const badge = getStatusBadge(status, score);
  const strokeColor = getHealthColor(score);

  // Life Remaining Estimation (Industrial nominal 45,000 hrs rating)
  const nominalLifeHours = 45000;
  const effectiveUsedHours = (cumulativeDamage * nominalLifeHours);
  const remainingHours = Math.max(0, nominalLifeHours - effectiveUsedHours);
  const remainingYears = (remainingHours / (24 * 365)).toFixed(1);

  // Gauge calculation (semi-circle SVG, radius=70, circum=pi*r ≈ 220)
  const radius = 64;
  const circumference = Math.PI * radius;
  const strokeDashoffset = circumference * (1 - Math.min(100, Math.max(0, score)) / 100);

  // Degradation trend steps for 4 intervals
  const trendSteps = [
    { label: '0h (Commissioning)', score: 100.0, current: false },
    { label: '5,000h (Break-in)', score: 98.2, current: false },
    { label: `Current (${Math.round(runtimeHours)}h)`, score: score, current: true },
    { label: 'Projected (30,000h)', score: Math.max(20, Math.round(score - (stressFactor * 35))), current: false },
    { label: 'End-of-Life (45,000h)', score: 30, current: false },
  ];

  return (
    <div className="compressor-hero-card">
      {/* Header bar */}
      <div className="comp-header">
        <div className="comp-title-group">
          <span className="comp-icon">⚙️</span>
          <div>
            <h3 className="comp-title">Compressor Health & Degradation Analytics</h3>
            <div className="comp-subtitle">
              Arrhenius Thermal Degradation Model (k = A · exp(-Ea / RT)) · Continuous Hardware Telemetry
            </div>
          </div>
        </div>

        <div className="comp-header-badges">
          <span className={`comp-status-badge ${badge.cls}`}>
            <span className="comp-dot" />
            {badge.label}
          </span>
          {demoMode && (
            <span className="demo-pill">DEMO ACCELERATED DEGRADATION</span>
          )}
        </div>
      </div>

      {/* Main 4-column diagnostic display */}
      <div className="comp-content-grid">
        {/* Column 1: Health Gauge (0-100) */}
        <div className="comp-gauge-col">
          <div className="gauge-label">HEALTH SCORE GAUGE</div>
          <div className="gauge-container">
            <svg viewBox="0 0 160 95" className="gauge-svg">
              {/* Background Arc */}
              <path
                d="M 16 85 A 64 64 0 0 1 144 85"
                fill="none"
                stroke="var(--color-surface)"
                strokeWidth="14"
                strokeLinecap="round"
              />
              {/* Threshold Arc (Warning at 65, Critical at 40) */}
              <path
                d="M 16 85 A 64 64 0 0 1 144 85"
                fill="none"
                stroke="rgba(233, 233, 237, 0.08)"
                strokeWidth="14"
                strokeLinecap="round"
              />
              {/* Value Arc */}
              <path
                d="M 16 85 A 64 64 0 0 1 144 85"
                fill="none"
                stroke={strokeColor}
                strokeWidth="14"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                style={{ transition: 'stroke-dashoffset 0.8s ease' }}
              />
            </svg>
            <div className="gauge-center-text">
              <span className="gauge-score-num" style={{ color: strokeColor }}>
                {score.toFixed(1)}
              </span>
              <span className="gauge-score-denom">/ 100</span>
            </div>
          </div>

          <div className="gauge-sub-info">
            <div className="gsi-row">
              <span>Arrhenius Stress:</span>
              <strong style={{ color: stressFactor > 1.2 ? 'var(--risk-watch)' : 'var(--color-text)' }}>
                {stressFactor.toFixed(3)}x nominal
              </strong>
            </div>
            <div className="gsi-row">
              <span>Cumulative Damage:</span>
              <strong>{(cumulativeDamage * 100).toFixed(2)}%</strong>
            </div>
          </div>
        </div>

        {/* Column 2: Degradation Trend */}
        <div className="comp-trend-col">
          <div className="gauge-label">DEGRADATION TREND (ARRHENIUS LIFE CYCLE)</div>
          <div className="trend-timeline">
            {trendSteps.map((step, idx) => (
              <div key={idx} className={`trend-step ${step.current ? 'current' : ''}`}>
                <div className="ts-marker">
                  <div
                    className="ts-dot"
                    style={{
                      background: getHealthColor(step.score),
                      borderColor: step.current ? 'var(--color-text)' : 'transparent',
                    }}
                  />
                  {idx < trendSteps.length - 1 && <div className="ts-line" />}
                </div>
                <div className="ts-info">
                  <span className="ts-name">{step.label}</span>
                  <span className="ts-val" style={{ color: getHealthColor(step.score) }}>
                    {step.score.toFixed(1)} / 100
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Column 3: Life Remaining & Thresholds */}
        <div className="comp-life-col">
          <div className="gauge-label">ESTIMATED COMPRESSOR LIFE REMAINING</div>
          <div className="life-card">
            <div className="life-hero-row">
              <span className="life-num">{Math.round(remainingHours).toLocaleString()}</span>
              <span className="life-unit">hours</span>
            </div>
            <div className="life-approx">≈ {remainingYears} years expected operating life</div>
          </div>

          <div className="threshold-card">
            <div className="tc-header">
              <span className="tc-title">MAINTENANCE ALERT THRESHOLD</span>
              <span className="tc-status text-safe">NOMINAL ENVELOPE</span>
            </div>
            <div className="tc-bar-track">
              {/* Critical zone 0-50 */}
              <div className="tc-zone critical" style={{ width: '40%' }} title="Critical Failure Zone (<40)" />
              {/* Warning zone 50-75 */}
              <div className="tc-zone warning" style={{ width: '25%' }} title="Maintenance Warning Zone (40-65)" />
              {/* Healthy zone 75-100 */}
              <div className="tc-zone healthy" style={{ width: '35%' }} title="Safe Operational Envelope (>65)" />
              {/* Current indicator */}
              <div
                className="tc-pointer"
                style={{ left: `${Math.min(98, Math.max(2, score))}%` }}
                title={`Current Score: ${score.toFixed(1)}`}
              />
            </div>
            <div className="tc-labels">
              <span>0 (Failure)</span>
              <span>40 (Critical)</span>
              <span>65 (Warning)</span>
              <span>100 (New)</span>
            </div>
          </div>
        </div>

        {/* Column 4: Live Hardware Readouts */}
        <div className="comp-diag-col">
          <div className="gauge-label">LIVE HARDWARE DIAGNOSTICS</div>
          <div className="diag-grid">
            <div className="diag-tile">
              <span className="dt-lbl">BODY TEMP</span>
              <span className="dt-val">{compTemp.toFixed(1)}°C</span>
              <span className="dt-sub">Limit 65.0°C</span>
            </div>
            <div className="diag-tile">
              <span className="dt-lbl">CURRENT DRAW</span>
              <span className="dt-val">{compCurrent.toFixed(1)} A</span>
              <span className="dt-sub">{compCurrent > 1.0 ? 'Running' : 'Standby'}</span>
            </div>
            <div className="diag-tile">
              <span className="dt-lbl">START-STOP CYCLES</span>
              <span className="dt-val">{cycles}</span>
              <span className="dt-sub">Thermal stress</span>
            </div>
            <div className="diag-tile">
              <span className="dt-lbl">RUN TIME</span>
              <span className="dt-val">{runtimeHours.toFixed(1)} h</span>
              <span className="dt-sub">Accumulated</span>
            </div>
          </div>

          <div className="diag-note">
            Hardware Interface: ACS712 current probe + DS18B20 core sensor ready via ESP32 edge link.
          </div>
        </div>
      </div>
    </div>
  );
}
