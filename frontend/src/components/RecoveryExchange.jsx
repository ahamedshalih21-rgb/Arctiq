import React from 'react';

/**
 * RecoveryExchange
 * ----------------
 * Displays the Risk Stock / Recovery Exchange module.
 * Shows at-risk batch listings derived from PyTorch LSTM spoilage predictions,
 * and simulated nearby buyer interest statuses.
 *
 * This is an industrial decision-support module, not a marketplace UI.
 * Reuses existing HMI CSS: .hmi-card, .hmi-section-title, .risk-badge,
 * .bi-row, .bi-label, .bi-value, .quick-stat patterns.
 * No new design language. No emojis.
 */

const RISK_ORDER = { Critical: 0, Watch: 1, Safe: 2 };

function riskClass(level) {
  if (level === 'CRITICAL' || level === 'Critical') return 'Critical';
  if (level === 'WATCH'    || level === 'Watch')    return 'Watch';
  return 'Safe';
}

function interestColor(status) {
  switch (status) {
    case 'INTERESTED':     return 'var(--risk-safe)';
    case 'NOT_INTERESTED': return 'var(--risk-critical)';
    case 'RESERVED':       return 'var(--color-accent)';
    case 'SOLD':           return 'var(--color-accent)';
    default:               return 'var(--color-neutral-600)';
  }
}

function listingStatusColor(status) {
  switch (status) {
    case 'ACTIVE':      return 'var(--color-neutral-400)';
    case 'INTERESTED':  return 'var(--risk-safe)';
    case 'RESERVED':    return 'var(--color-accent)';
    case 'SOLD':        return 'var(--color-accent)';
    case 'EXPIRED':     return 'var(--color-neutral-600)';
    default:            return 'var(--color-neutral-600)';
  }
}

export default function RecoveryExchange({ listings, buyers }) {
  const hasListings = listings && listings.length > 0;
  const hasBuyers   = buyers   && buyers.length > 0;

  return (
    <div className="hmi-card">

      {/* ── Section: Risk Stock Listings ─────────────────────────────── */}
      <div className="hmi-section-title">Risk Stock / Recovery Exchange</div>

      {!hasListings ? (
        <div className="bi-row" style={{ borderBottom: 'none' }}>
          <span className="bi-label" style={{ color: 'var(--color-neutral-600)' }}>
            No at-risk batches — all batches within safe threshold
          </span>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="re-table">
            <thead>
              <tr>
                <th>Batch</th>
                <th>Produce</th>
                <th>Risk</th>
                <th>Remaining</th>
                <th>Qty</th>
                <th>Recovery Price</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {listings.map(listing => {
                const rc = riskClass(listing.risk_level);
                return (
                  <tr key={listing.batch_id}>
                    <td>
                      <span className="bi-value" style={{ fontSize: '0.68rem' }}>
                        {listing.batch_id}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.68rem', color: 'var(--color-neutral-400)' }}>
                        {listing.display_name}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`risk-badge ${rc}`}
                        style={{ fontSize: '0.58rem', padding: '1px 5px' }}
                      >
                        <span className="risk-dot" />
                        {listing.risk_level.toUpperCase()}
                      </span>
                    </td>
                    <td>
                      <span className="bi-value" style={{ fontSize: '0.68rem' }}>
                        {listing.remaining_hours != null
                          ? `${listing.remaining_hours.toFixed(1)} h`
                          : '--'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.68rem', color: 'var(--color-neutral-400)', fontFamily: 'var(--font-mono)' }}>
                        {listing.batch_weight_kg != null ? `${listing.batch_weight_kg} kg` : '--'}
                      </span>
                    </td>
                    <td>
                      <span className="bi-value" style={{ fontSize: '0.68rem', color: 'var(--risk-safe)' }}>
                        {listing.suggested_recovery_price != null
                          ? `\u20B9${listing.suggested_recovery_price.toLocaleString('en-IN')}`
                          : '--'}
                      </span>
                    </td>
                    <td>
                      <span
                        style={{
                          fontSize: '0.62rem',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          letterSpacing: '0.06em',
                          color: listingStatusColor(listing.listing_status),
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        {listing.listing_status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Section: Nearby Buyers ────────────────────────────────────── */}
      <div
        className="hmi-section-title"
        style={{ marginTop: hasListings ? 0 : undefined }}
      >
        Nearby Buyers
      </div>

      {!hasBuyers ? (
        <div className="bi-row" style={{ borderBottom: 'none' }}>
          <span className="bi-label">No buyer data available</span>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="re-table">
            <thead>
              <tr>
                <th>Buyer</th>
                <th>Type</th>
                <th>Distance</th>
                <th>Interest</th>
              </tr>
            </thead>
            <tbody>
              {buyers.map(buyer => (
                <tr key={buyer.buyer_id}>
                  <td>
                    <span className="bi-value" style={{ fontSize: '0.68rem' }}>
                      {buyer.buyer_name}
                    </span>
                  </td>
                  <td>
                    <span style={{ fontSize: '0.65rem', color: 'var(--color-neutral-400)' }}>
                      {buyer.buyer_type}
                    </span>
                  </td>
                  <td>
                    <span style={{ fontSize: '0.65rem', fontFamily: 'var(--font-mono)', color: 'var(--color-neutral-400)' }}>
                      {buyer.distance_km != null ? `${buyer.distance_km} km` : '--'}
                    </span>
                  </td>
                  <td>
                    <span
                      style={{
                        fontSize: '0.62rem',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        color: interestColor(buyer.interest_status),
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {buyer.interest_status || 'PENDING'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Note */}
      <div
        style={{
          padding: 'var(--space-3) var(--space-6)',
          borderTop: '1px solid var(--color-divider)',
          fontSize: '0.58rem',
          color: 'var(--color-neutral-600)',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        Prototype simulation — buyer responses and pricing are illustrative only
      </div>

    </div>
  );
}
