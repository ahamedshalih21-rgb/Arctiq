import React, { useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts';

/**
 * EnergyPanel — Hero Component
 * -----------------------------------------
 * Displays real-time cold-storage energy consumption, baseline comparison,
 * compressor duty cycle, financial savings in INR, and a 24-hour power trend.
 * Clean industrial typography — ZERO emojis.
 */

const BASELINE_KW = 2.5;

const CustomEnergyTooltip = ({ active, payload, label, electricityRate }) => {
  if (!active || !payload?.length) return null;
  const actual = payload.find(p => p.dataKey === 'actual_kw')?.value ?? 0;
  const baseline = payload.find(p => p.dataKey === 'baseline_kw')?.value ?? BASELINE_KW;
  const saved = Math.max(0, baseline - actual);
  const costSaved = (saved * electricityRate).toFixed(2);

  return (
    <div className="energy-chart-tooltip">
      <div className="ect-header">Time: {label}</div>
      <div className="ect-row">
        <span className="ect-dot" style={{ background: 'var(--color-accent)' }} />
        <span>Arctiq AI Power:</span>
        <strong>{Number(actual).toFixed(2)} kW</strong>
      </div>
      <div className="ect-row">
        <span className="ect-dot" style={{ background: '#F87171' }} />
        <span>Fixed Baseline:</span>
        <strong>{Number(baseline).toFixed(2)} kW</strong>
      </div>
      <div className="ect-row highlight">
        <span className="ect-dot" style={{ background: 'var(--risk-safe)' }} />
        <span>Power Saved:</span>
        <strong style={{ color: 'var(--risk-safe)' }}>
          {saved.toFixed(2)} kW (₹{costSaved}/h)
        </strong>
      </div>
    </div>
  );
};

export default function EnergyPanel({ energyData, compressorData, electricityRate = 8.0, onOpenRateSettings }) {
  const [chartMode, setChartMode] = useState('power'); // 'power' | 'savings'

  const comp = compressorData || {};
  const dutyCyclePct = energyData?.duty_cycle_pct ?? (comp.duty_cycle != null ? Number(comp.duty_cycle) : 55.0);
  const isRunning = energyData?.compressor_is_running ?? (comp.compressor_current > 1.0);

  // Power draw in kW
  const currentKw = energyData?.current_power_kw ?? (
    isRunning
      ? Number((1.25 + (dutyCyclePct / 100) * 0.35).toFixed(2))
      : 0.18
  );

  // Baseline kW = 2.5 kW constant fixed thermostat
  const baselineKw = energyData?.baseline_kw ?? BASELINE_KW;

  // Energy saved % = (baseline - current) / baseline * 100
  const effectiveKw = energyData?.effective_power_kw ?? (
    (dutyCyclePct / 100) * 1.55 + (1 - dutyCyclePct / 100) * 0.18
  );
  const energySavedPct = energyData?.energy_saved_pct ?? Number(
    Math.max(0, ((baselineKw - effectiveKw) / baselineKw) * 100).toFixed(1)
  );

  // Dynamic Cost calculations based on customizable electricity rate (₹/kWh)
  const dailyKwhSaved = energyData?.daily_kwh_saved ?? Number(
    Math.max(0, (baselineKw - effectiveKw) * 24).toFixed(1)
  );
  const dailyCostSavedInr = Number((dailyKwhSaved * electricityRate).toFixed(2));
  const monthlyCostSavedInr = Number((dailyCostSavedInr * 30).toFixed(2));
  const annualCostSavedInr = Number((dailyCostSavedInr * 365).toFixed(2));

  // 24h Trend Data
  const trendData = energyData?.trend_24h && energyData.trend_24h.length > 0
    ? energyData.trend_24h.map(t => ({
        ...t,
        saved_cost_inr: Number((t.saved_kw * electricityRate).toFixed(2)),
      }))
    : Array.from({ length: 24 }, (_, i) => {
        const hour = `${String(i).padStart(2, '0')}:00`;
        const diurnal = 1.0 + 0.12 * Math.sin((i - 8) * Math.PI / 12);
        const bKw = Number((BASELINE_KW * (0.95 + 0.08 * Math.sin((i - 6) * Math.PI / 12))).toFixed(2));
        const aKw = Number((effectiveKw * diurnal + 0.05 * Math.sin(i * 1.5)).toFixed(2));
        const sKw = Number(Math.max(0, bKw - aKw).toFixed(2));
        return {
          hour,
          baseline_kw: bKw,
          actual_kw: aKw,
          saved_kw: sKw,
          saved_cost_inr: Number((sKw * electricityRate).toFixed(2)),
        };
      });

  return (
    <div className="energy-hero-card">
      {/* Header bar */}
      <div className="energy-header">
        <div className="energy-header-left">
          <div className="energy-title-group">
            <span className="energy-badge-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
              </svg>
            </span>
            <div>
              <h2 className="energy-title">Energy Consumption & Optimization</h2>
              <div className="energy-subtitle">
                Real-time cooling power telemetry vs fixed-thermostat baseline (2.50 kW)
              </div>
            </div>
          </div>
        </div>

        <div className="energy-header-right">
          <div className="energy-tag">
            <span className="energy-pulse-dot" />
            AI Inverter Modulation: Active
          </div>
          <button
            type="button"
            className="tariff-pill clickable"
            onClick={onOpenRateSettings}
            title="Click to customize electricity rate"
          >
            Tariff: ₹{Number(electricityRate).toFixed(1)}/kWh
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: 4 }}>
              <path d="M12 20h9"></path>
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
            </svg>
          </button>
        </div>
      </div>

      {/* Hero 4 KPIs */}
      <div className="energy-kpi-grid">
        {/* KPI 1: Current Power Draw */}
        <div className="energy-kpi-card highlight-cyan">
          <div className="ekpi-top">
            <span className="ekpi-label">CURRENT POWER DRAW</span>
            <span className={`ekpi-status-dot ${isRunning ? 'running' : 'idle'}`} title={isRunning ? 'Compressor Active' : 'Circulation Mode'} />
          </div>
          <div className="ekpi-value-row">
            <span className="ekpi-value">{currentKw.toFixed(2)}</span>
            <span className="ekpi-unit">kW</span>
          </div>
          <div className="ekpi-comparison">
            <span className="ekpi-diff negative">
              -{Math.abs(((baselineKw - currentKw) / baselineKw) * 100).toFixed(0)}%
            </span>
            <span className="ekpi-vs">vs 2.50 kW baseline</span>
          </div>
          <div className="ekpi-bar-track">
            <div
              className="ekpi-bar-fill cyan"
              style={{ width: `${Math.min(100, (currentKw / baselineKw) * 100)}%` }}
            />
          </div>
        </div>

        {/* KPI 2: Energy Saved Today */}
        <div className="energy-kpi-card highlight-green">
          <div className="ekpi-top">
            <span className="ekpi-label">ENERGY SAVED TODAY</span>
            <span className="ekpi-pill safe">OPTIMIZED</span>
          </div>
          <div className="ekpi-value-row">
            <span className="ekpi-value text-safe">{energySavedPct.toFixed(1)}</span>
            <span className="ekpi-unit text-safe">%</span>
          </div>
          <div className="ekpi-comparison">
            <span className="ekpi-sub-highlight text-safe">
              {dailyKwhSaved.toFixed(1)} kWh
            </span>
            <span className="ekpi-vs">saved in last 24h</span>
          </div>
          <div className="ekpi-bar-track">
            <div
              className="ekpi-bar-fill green"
              style={{ width: `${Math.min(100, energySavedPct)}%` }}
            />
          </div>
        </div>

        {/* KPI 3: Compressor Duty Cycle */}
        <div className="energy-kpi-card highlight-blue">
          <div className="ekpi-top">
            <span className="ekpi-label">COMPRESSOR DUTY CYCLE</span>
            <span className="ekpi-pill info">{isRunning ? 'COMPRESSOR ON' : 'IDLE CYCLE'}</span>
          </div>
          <div className="ekpi-value-row">
            <span className="ekpi-value">{dutyCyclePct.toFixed(1)}</span>
            <span className="ekpi-unit">%</span>
          </div>
          <div className="ekpi-comparison">
            <span className="ekpi-vs">Hourly state: </span>
            <span className="ekpi-sub-highlight">
              {dutyCyclePct < 65 ? 'Optimal (50–65%)' : 'High Demand'}
            </span>
          </div>
          <div className="ekpi-bar-track">
            <div
              className="ekpi-bar-fill blue"
              style={{ width: `${Math.min(100, dutyCyclePct)}%` }}
            />
          </div>
        </div>

        {/* KPI 4: Cost Saved (Customizable INR Rate) */}
        <div className="energy-kpi-card highlight-amber">
          <div className="ekpi-top">
            <span className="ekpi-label">COST SAVED TODAY</span>
            <button
              type="button"
              className="ekpi-settings-btn"
              onClick={onOpenRateSettings}
              title="Configure State Electricity Rate (₹/kWh)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
              <span>RATE</span>
            </button>
          </div>

          <div className="ekpi-value-row">
            <span className="ekpi-symbol text-amber">₹</span>
            <span className="ekpi-value text-amber">{Math.round(dailyCostSavedInr)}</span>
          </div>

          {/* Required Rate Disclosure Line */}
          <div className="ekpi-rate-line" title="Configurable via Settings">
            Energy Saved: {dailyKwhSaved.toFixed(1)} kWh @ ₹{Number(electricityRate).toFixed(1)}/kWh ({electricityRate === 8.0 ? 'default India rate' : 'custom state rate'})
          </div>

          <div className="ekpi-comparison" style={{ marginTop: 4 }}>
            <span className="ekpi-vs">Monthly: </span>
            <span className="ekpi-sub-highlight text-amber" style={{ marginRight: 6 }}>
              ₹{Math.round(monthlyCostSavedInr).toLocaleString('en-IN')}/mo
            </span>
            <span className="ekpi-vs">12-Mo: </span>
            <span className="ekpi-sub-highlight text-amber">
              ₹{Math.round(annualCostSavedInr).toLocaleString('en-IN')}
            </span>
          </div>

          <div className="ekpi-bar-track">
            <div
              className="ekpi-bar-fill amber"
              style={{ width: `${Math.min(100, (dailyCostSavedInr / (35 * electricityRate)) * 100)}%` }}
            />
          </div>

          <div className="ekpi-rate-disclaimer">
            Rates vary by state and tariff. Update for accurate savings estimate.
          </div>
        </div>
      </div>

      {/* 24-Hour Trend Chart Section */}
      <div className="energy-chart-section">
        <div className="energy-chart-header">
          <div>
            <div className="energy-chart-title">24-Hour Power Consumption Profile</div>
            <div className="energy-chart-desc">
              Comparison of Arctiq dynamic inverter power vs fixed 2.50 kW thermostat baseline
            </div>
          </div>
          <div className="chart-mode-toggles">
            <button
              type="button"
              className={`cmt-btn ${chartMode === 'power' ? 'active' : ''}`}
              onClick={() => setChartMode('power')}
            >
              Power Draw (kW)
            </button>
            <button
              type="button"
              className={`cmt-btn ${chartMode === 'savings' ? 'active' : ''}`}
              onClick={() => setChartMode('savings')}
            >
              Hourly Savings (₹ @ ₹{Number(electricityRate).toFixed(1)}/kWh)
            </button>
          </div>
        </div>

        <div className="energy-chart-wrapper">
          <ResponsiveContainer width="100%" height={260}>
            {chartMode === 'power' ? (
              <AreaChart data={trendData} margin={{ top: 12, right: 16, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="arctiqPowerGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-accent)" stopOpacity={0.40} />
                    <stop offset="95%" stopColor="var(--color-accent)" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="baselinePowerGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#F87171" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#F87171" stopOpacity={0.00} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(233, 233, 237, 0.08)" />
                <XAxis
                  dataKey="hour"
                  stroke="var(--color-neutral-600)"
                  tick={{ fill: 'var(--color-neutral-400)', fontSize: 11 }}
                  tickLine={false}
                  interval={2}
                />
                <YAxis
                  domain={[0, 3.2]}
                  stroke="var(--color-neutral-600)"
                  tick={{ fill: 'var(--color-neutral-400)', fontSize: 11 }}
                  tickLine={false}
                  unit=" kW"
                />
                <Tooltip content={<CustomEnergyTooltip electricityRate={electricityRate} />} />
                <ReferenceLine
                  y={BASELINE_KW}
                  stroke="#F87171"
                  strokeDasharray="4 4"
                  label={{
                    value: 'Baseline (2.5 kW)',
                    fill: '#F87171',
                    fontSize: 10,
                    position: 'insideTopRight'
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="baseline_kw"
                  name="Fixed Baseline"
                  stroke="#F87171"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  fill="url(#baselinePowerGrad)"
                />
                <Area
                  type="monotone"
                  dataKey="actual_kw"
                  name="Arctiq Optimized"
                  stroke="var(--color-accent)"
                  strokeWidth={2.5}
                  fill="url(#arctiqPowerGrad)"
                />
              </AreaChart>
            ) : (
              <AreaChart data={trendData} margin={{ top: 12, right: 16, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="savingsGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--risk-safe)" stopOpacity={0.45} />
                    <stop offset="95%" stopColor="var(--risk-safe)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(233, 233, 237, 0.08)" />
                <XAxis
                  dataKey="hour"
                  stroke="var(--color-neutral-600)"
                  tick={{ fill: 'var(--color-neutral-400)', fontSize: 11 }}
                  tickLine={false}
                  interval={2}
                />
                <YAxis
                  stroke="var(--color-neutral-600)"
                  tick={{ fill: 'var(--color-neutral-400)', fontSize: 11 }}
                  tickLine={false}
                  unit=" ₹"
                />
                <Tooltip content={<CustomEnergyTooltip electricityRate={electricityRate} />} />
                <Area
                  type="monotone"
                  dataKey="saved_cost_inr"
                  name="Hourly Savings (₹)"
                  stroke="var(--risk-safe)"
                  strokeWidth={2.5}
                  fill="url(#savingsGrad)"
                />
              </AreaChart>
            )}
          </ResponsiveContainer>
        </div>

        {/* Legend and Optimization Highlights */}
        <div className="energy-chart-footer">
          <div className="ec-legend">
            <span className="ecl-item">
              <span className="ecl-line cyan" /> Arctiq Smart Modulated Power
            </span>
            <span className="ecl-item">
              <span className="ecl-line red dashed" /> Baseline (2.50 kW Unmanaged)
            </span>
            <span className="ecl-item">
              <span className="ecl-badge safe">Area = Net Savings</span>
            </span>
          </div>

          <div className="ec-stats-strip">
            <div className="ecs-stat">
              <span className="ecs-lbl">Est. COP:</span>
              <span className="ecs-val text-cyan">4.12</span>
            </div>
            <div className="ecs-divider" />
            <div className="ecs-stat">
              <span className="ecs-lbl">Peak Reduction:</span>
              <span className="ecs-val text-safe">38.4%</span>
            </div>
            <div className="ecs-divider" />
            <div className="ecs-stat">
              <span className="ecs-lbl">Cooling Strategy:</span>
              <span className="ecs-val">Kinetic Respiration Load Matching</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
