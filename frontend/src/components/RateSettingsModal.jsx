import React, { useState, useEffect } from 'react';

/**
 * RateSettingsModal
 * -----------------------------------------
 * Customizable Electricity Rate (₹/kWh) Modal.
 * Saves preference to localStorage as 'electricityRate'.
 * Plain text / SVG only — NO emojis.
 */

const STATE_PRESETS = [
  { name: 'National Avg (Default)', rate: 8.0 },
  { name: 'Tamil Nadu (TANGEDCO)', rate: 6.5 },
  { name: 'Gujarat (UGVCL/DGVCL)', rate: 7.2 },
  { name: 'Karnataka (BESCOM)', rate: 8.5 },
  { name: 'Maharashtra (MSEDCL)', rate: 9.5 },
  { name: 'Delhi / NCR (BSES)', rate: 10.0 },
];

export default function RateSettingsModal({ isOpen, onClose, currentRate, onSaveRate }) {
  const [rateInput, setRateInput] = useState(String(currentRate || 8.0));
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (isOpen) {
      setRateInput(String(currentRate || 8.0));
      setErrorMsg('');
    }
  }, [isOpen, currentRate]);

  if (!isOpen) return null;

  const handleSave = (valToSave) => {
    const num = parseFloat(valToSave !== undefined ? valToSave : rateInput);
    if (isNaN(num) || num <= 0 || num > 100) {
      setErrorMsg('Please enter a valid rate between ₹1 and ₹100 per kWh.');
      return;
    }
    onSaveRate(num);
    onClose();
  };

  const handlePresetSelect = (presetRate) => {
    setRateInput(String(presetRate));
    setErrorMsg('');
  };

  const handleResetDefault = () => {
    setRateInput('8.0');
    handleSave(8.0);
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="rate-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="rate-modal-header">
          <div className="rate-modal-title-row">
            <span className="rate-modal-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
            </span>
            <div>
              <div className="rate-modal-title">Electricity Tariff Settings</div>
              <div className="rate-modal-subtitle">Configure regional power cost for financial savings calculations</div>
            </div>
          </div>
          <button className="rate-modal-close" onClick={onClose} aria-label="Close modal">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="rate-modal-body">
          <label className="rate-input-label" htmlFor="electricity-rate-input">
            Electricity Rate (₹/kWh)
          </label>
          <div className="rate-input-group">
            <span className="rate-input-prefix">₹</span>
            <input
              id="electricity-rate-input"
              type="number"
              step="0.1"
              min="1"
              max="50"
              className="rate-number-input"
              value={rateInput}
              onChange={(e) => {
                setRateInput(e.target.value);
                setErrorMsg('');
              }}
              placeholder="8.0"
              autoFocus
            />
            <span className="rate-input-suffix">/ kWh</span>
          </div>

          {errorMsg && <div className="rate-error-text">{errorMsg}</div>}

          {/* Preset Buttons */}
          <div className="rate-presets-section">
            <div className="rate-presets-label">State / Regional Commercial Presets</div>
            <div className="rate-presets-grid">
              {STATE_PRESETS.map((preset) => {
                const isSelected = parseFloat(rateInput) === preset.rate;
                return (
                  <button
                    key={preset.name}
                    type="button"
                    className={`rate-preset-btn ${isSelected ? 'active' : ''}`}
                    onClick={() => handlePresetSelect(preset.rate)}
                  >
                    <span className="rpb-name">{preset.name}</span>
                    <span className="rpb-rate">₹{preset.rate.toFixed(1)}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Disclaimer */}
          <div className="rate-disclaimer-box">
            <div className="rdb-title">Tariff Notice</div>
            <div className="rdb-text">
              Rates vary by state and tariff. Update for accurate savings estimate.
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="rate-modal-footer">
          <button type="button" className="rate-btn secondary" onClick={handleResetDefault}>
            Reset Default (₹8/kWh)
          </button>
          <div className="rate-modal-actions-right">
            <button type="button" className="rate-btn cancel" onClick={onClose}>
              Cancel
            </button>
            <button type="button" className="rate-btn primary" onClick={() => handleSave()}>
              Save & Apply Rate
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
