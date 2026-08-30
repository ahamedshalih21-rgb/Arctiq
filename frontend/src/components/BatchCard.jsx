import React from 'react';

export default function BatchCard({ metadata }) {
  if (!metadata) return null;

  const since = metadata.storage_since
    ? new Date(metadata.storage_since).toLocaleString('en-US', { dateStyle: 'short', timeStyle: 'short' })
    : '--';

  const storedHours = metadata.storage_since
    ? ((Date.now() - new Date(metadata.storage_since).getTime()) / 3600000).toFixed(1)
    : '--';

  return (
    <div className="batch-info-card glass-card">
      <div className="bi-title">📦 Batch Information</div>
      <div className="bi-row">
        <span className="bi-label">Batch ID</span>
        <span className="bi-value">{metadata.batch_id}</span>
      </div>
      <div className="bi-row">
        <span className="bi-label">Produce</span>
        <span className="bi-value">{metadata.emoji} {metadata.display_name}</span>
      </div>
      <div className="bi-row">
        <span className="bi-label">Weight</span>
        <span className="bi-value">{metadata.batch_weight_kg} kg</span>
      </div>
      <div className="bi-row">
        <span className="bi-label">Value/kg</span>
        <span className="bi-value">${metadata.value_per_kg?.toFixed(2)}</span>
      </div>
      <div className="bi-row">
        <span className="bi-label">Stored since</span>
        <span className="bi-value">{since}</span>
      </div>
      <div className="bi-row">
        <span className="bi-label">Hours in storage</span>
        <span className="bi-value">{storedHours}h</span>
      </div>
      <div className="bi-row">
        <span className="bi-label">Fault active</span>
        <span className="bi-value" style={{ color: metadata.fault_active ? '#ff4757' : '#00d68f' }}>
          {metadata.fault_active ? `⚠️ YES (${metadata.fault_speed}x)` : '✅ No'}
        </span>
      </div>
    </div>
  );
}
