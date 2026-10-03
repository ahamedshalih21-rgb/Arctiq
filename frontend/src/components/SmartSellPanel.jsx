import React, { useState } from 'react';

/**
 * SmartSellPanel
 * ---------------
 * Displays ranked SmartSell recommendations based on LSTM spoilage predictions.
 * Follows HMI design language: no emojis, monospace data values, uppercase labels.
 */

const PRIORITY_COLORS = {
  'SELL NOW':  'var(--risk-critical)',
  'SELL SOON': 'var(--risk-high)',
  'PROMOTE':   'var(--risk-watch)',
  'HOLD':      'var(--risk-safe)',
};

const STAGE_COLORS = {
  'CRITICAL':      'var(--risk-critical)',
  'HIGH_RISK':     'var(--risk-high)',
  'EARLY_WARNING': 'var(--risk-watch)',
  'WATCH':         'var(--risk-watch)',
  'MONITOR':       'var(--color-accent)',
  'SAFE':          'var(--risk-safe)',
  'SPOILED':       'var(--color-neutral-600)',
};

function fmt(n, decimals = 0) {
  if (n == null) return '--';
  return Number(n).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Single recommendation card (top priority batch) */
function TopRecommendationCard({ rec, allRecs }) {
  if (!rec) return null;

  const priorityColor = PRIORITY_COLORS[rec.priority_action] || 'var(--color-neutral-400)';
  const stageColor    = STAGE_COLORS[rec.warning_stage] || 'var(--color-neutral-400)';

  return (
    <div className="ss-top-card">
      {/* Header */}
      <div className="ss-top-header">
        <div>
          <div className="ss-top-rank">RANK 1 — HIGHEST PRIORITY</div>
          <div className="ss-top-product">{rec.display_name}</div>
          <div className="ss-top-batch">{rec.batch_id}</div>
        </div>
        <div className="ss-priority-badge" style={{ color: priorityColor, borderColor: priorityColor }}>
          {rec.priority_action}
        </div>
      </div>

      {/* Two-stage warning */}
      <div className="ss-warning-row">
        <div className="ss-warning-block">
          <div className="ss-warn-label">MODEL PREDICTION</div>
          <div className="ss-warn-value" style={{ color: stageColor }}>
            {rec.model_hours_remaining != null ? `${rec.model_hours_remaining.toFixed(1)} h` : '--'}
          </div>
          <div className="ss-warn-sublabel">Model-driven operational reference</div>
        </div>
        <div className="ss-warning-divider" />
        <div className="ss-warning-block">
          <div className="ss-warn-label">PROJECTED HORIZON</div>
          <div className="ss-warn-value" style={{ color: 'var(--risk-watch)' }}>
            {rec.projected_risk_horizon_hours != null ? `~${Math.round(rec.projected_risk_horizon_hours)} h` : '--'}
          </div>
          <div className="ss-warn-sublabel">Trend-based early warning estimate</div>
        </div>
        <div className="ss-warning-divider" />
        <div className="ss-warning-block">
          <div className="ss-warn-label">PRIORITY SCORE</div>
          <div className="ss-warn-value" style={{ color: priorityColor }}>
            {rec.sell_priority_score != null ? `${rec.sell_priority_score.toFixed(0)}/100` : '--'}
          </div>
          <div className="ss-warn-sublabel">Composite sell urgency score</div>
        </div>
      </div>

      {/* Pricing grid */}
      <div className="ss-pricing-grid">
        <div className="ss-pricing-item">
          <div className="ss-p-label">MARKET PRICE</div>
          <div className="ss-p-value">Rs{fmt(rec.market_price_per_kg, 0)}<span className="ss-p-unit">/kg</span></div>
        </div>
        <div className="ss-pricing-item">
          <div className="ss-p-label">PURCHASE COST</div>
          <div className="ss-p-value">Rs{fmt(rec.purchase_cost_per_kg, 0)}<span className="ss-p-unit">/kg</span></div>
        </div>
        <div className="ss-pricing-item">
          <div className="ss-p-label">REC. PRICE</div>
          <div className="ss-p-value" style={{ color: 'var(--risk-safe)' }}>
            Rs{fmt(rec.recommended_price_per_kg, 0)}<span className="ss-p-unit">/kg</span>
          </div>
        </div>
        <div className="ss-pricing-item">
          <div className="ss-p-label">DISCOUNT</div>
          <div className="ss-p-value" style={{ color: 'var(--risk-watch)' }}>
            {fmt(rec.discount_percent, 1)}%
          </div>
        </div>
        <div className="ss-pricing-item">
          <div className="ss-p-label">STOCK</div>
          <div className="ss-p-value">{fmt(rec.quantity_kg, 0)}<span className="ss-p-unit"> kg</span></div>
        </div>
        <div className="ss-pricing-item">
          <div className="ss-p-label">DEMAND</div>
          <div className="ss-p-value">{fmt(rec.demand_score, 0)}<span className="ss-p-unit">/100</span></div>
        </div>
        <div className="ss-pricing-item">
          <div className="ss-p-label">WASTE RISK</div>
          <div className="ss-p-value" style={{ color: 'var(--risk-critical)' }}>
            Rs{fmt(rec.expected_waste_inr, 0)}
          </div>
        </div>
        <div className="ss-pricing-item">
          <div className="ss-p-label">MARGIN/KG</div>
          <div
            className="ss-p-value"
            style={{ color: rec.below_cost_sale ? 'var(--risk-critical)' : 'var(--color-accent)' }}
          >
            Rs{fmt(rec.estimated_margin_per_kg, 0)}
            {rec.below_cost_sale && <span style={{ fontSize: '0.55rem', marginLeft: 3 }}>BELOW COST</span>}
          </div>
        </div>
      </div>

      {/* Reason factors */}
      {rec.reason_factors && rec.reason_factors.length > 0 && (
        <div className="ss-reasons">
          <div className="ss-reasons-label">DECISION FACTORS</div>
          <ul className="ss-reason-list">
            {rec.reason_factors.map((f, i) => (
              <li key={i} className="ss-reason-item">{f}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Pricing rationale */}
      {rec.pricing_rationale && (
        <div className="ss-rationale">{rec.pricing_rationale}</div>
      )}

      {/* Below-cost warning */}
      {rec.below_cost_sale && rec.below_cost_reason && (
        <div className="ss-below-cost-note">{rec.below_cost_reason}</div>
      )}
    </div>
  );
}

/** Ranked summary row */
function RankedRow({ rec }) {
  const priorityColor = PRIORITY_COLORS[rec.priority_action] || 'var(--color-neutral-400)';
  const stageColor    = STAGE_COLORS[rec.warning_stage] || 'var(--color-neutral-400)';

  return (
    <div className="ss-ranked-row">
      <div className="ss-ranked-rank">#{rec.rank}</div>
      <div className="ss-ranked-product">
        <div className="ss-ranked-name">{rec.display_name}</div>
        <div className="ss-ranked-batch">{rec.batch_id}</div>
      </div>
      <div className="ss-ranked-stage" style={{ color: stageColor }}>
        {rec.warning_stage?.replace('_', ' ')}
      </div>
      <div className="ss-ranked-hours">
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }}>
          {rec.model_hours_remaining != null ? `${rec.model_hours_remaining.toFixed(1)}h` : '--'}
        </div>
        <div style={{ fontSize: '0.58rem', color: 'var(--color-neutral-600)' }}>model</div>
      </div>
      <div className="ss-ranked-price" style={{ color: 'var(--risk-safe)' }}>
        Rs{fmt(rec.recommended_price_per_kg, 0)}/kg
      </div>
      <div className="ss-ranked-discount">
        {fmt(rec.discount_percent, 0)}% off
      </div>
      <div className="ss-ranked-score" style={{ color: priorityColor }}>
        {rec.sell_priority_score?.toFixed(0)}
      </div>
      <div className="ss-ranked-action" style={{ color: priorityColor }}>
        {rec.priority_action}
      </div>
    </div>
  );
}

export default function SmartSellPanel({ recommendations, loading }) {
  if (loading) {
    return (
      <div className="hmi-card">
        <div className="hmi-section-title">SMARTSELL RECOMMENDATIONS</div>
        <div className="ss-loading">Loading recommendations...</div>
      </div>
    );
  }

  if (!recommendations || recommendations.length === 0) {
    return (
      <div className="hmi-card">
        <div className="hmi-section-title">SMARTSELL RECOMMENDATIONS</div>
        <div className="ss-loading">No recommendation data available. Ensure backend is running.</div>
      </div>
    );
  }

  const topRec  = recommendations[0];
  const allRecs = recommendations;

  return (
    <div className="hmi-card">
      <div className="hmi-section-title">SMARTSELL RECOMMENDATIONS</div>
      <div className="ss-horizon-note">
        <span style={{ color: 'var(--color-neutral-600)' }}>
          Model prediction: PyTorch LSTM-driven operational reference.
          Projected horizon: trend-based early warning estimate (not model-validated).
        </span>
      </div>

      {/* Top priority card */}
      <TopRecommendationCard rec={topRec} allRecs={allRecs} />

      {/* Ranked summary — all batches */}
      {allRecs.length > 1 && (
        <div className="ss-ranked-section">
          <div className="ss-ranked-header-row">
            <span>#</span>
            <span>PRODUCT</span>
            <span>STATUS</span>
            <span>MODEL HRS</span>
            <span>REC. PRICE</span>
            <span>DISC.</span>
            <span>SCORE</span>
            <span>ACTION</span>
          </div>
          {allRecs.map(rec => (
            <RankedRow
              key={rec.batch_id}
              rec={rec}
            />
          ))}
        </div>
      )}

      <div className="ss-footer-note">
        Demand scores and quantities are stateful and evolve gradually.
        SmartSell scores update on each poll cycle. Pricing is illustrative.
      </div>
    </div>
  );
}
