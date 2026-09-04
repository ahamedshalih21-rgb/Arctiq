import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

/**
 * SensorChart — with EMA display smoothing
 * -----------------------------------------
 * Applies a client-side Exponential Moving Average (EMA) to the history
 * data before rendering. This is for display/visual purposes only.
 *
 * IMPORTANT: The raw data still comes from the backend and is used by
 * the ML pipeline. This smoothing is applied only to the chart display.
 * The backend already applies EMA to the simulator's output (simulator.py),
 * so a lighter alpha (0.4) is used here to avoid over-smoothing.
 *
 * During fault events the backend uses a higher alpha so excursions still
 * appear clearly on the chart — fault events will NOT be hidden by this
 * client-side smoothing pass.
 */

const EMA_ALPHA = 0.40;   // display-only smoothing; 0.4 = moderate smoothing

function applyEMA(data, alpha = EMA_ALPHA) {
  if (!data || data.length === 0) return [];
  const result = [];
  let ema_temp = data[0].temperature;
  let ema_hum  = data[0].humidity;

  for (let i = 0; i < data.length; i++) {
    ema_temp = alpha * data[i].temperature + (1 - alpha) * ema_temp;
    ema_hum  = alpha * data[i].humidity   + (1 - alpha) * ema_hum;
    result.push({
      ...data[i],
      temperature: Math.round(ema_temp * 100) / 100,
      humidity:    Math.round(ema_hum  * 100) / 100,
    });
  }
  return result;
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="custom-tooltip">
      <div className="ct-time">Reading t-{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="ct-row">
          <div className="ct-dot" style={{ background: p.stroke }} />
          <span style={{ color: p.stroke }}>
            {p.dataKey === 'temperature'
              ? `${Number(p.value).toFixed(1)} C`
              : `${Number(p.value).toFixed(1)} %`}
          </span>
        </div>
      ))}
    </div>
  );
};

export default function SensorChart({ history, produceConfig }) {
  // Apply EMA smoothing for display — does NOT affect backend predictions
  const smoothed = applyEMA(history, EMA_ALPHA);

  const data = smoothed.map((r, i) => ({
    index:       history.length - i,
    temperature: r.temperature,
    humidity:    r.humidity,
  }));

  return (
    <div className="chart-card">
      <div className="chart-header">
        <div className="chart-title">
          Sensor Telemetry — {produceConfig?.display_name}
        </div>
        <div className="chart-legend">
          <div className="legend-item">
            <div className="legend-line" style={{ background: '#F87171' }} />
            Temp C
          </div>
          <div className="legend-item">
            <div className="legend-line" style={{ background: '#4FB6C9' }} />
            Humidity %
          </div>
        </div>
      </div>

      <div className="chart-body">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
            <CartesianGrid strokeDasharray="4 4" vertical={false} />
            <XAxis
              dataKey="index"
              reversed
              tick={{ fontSize: 10 }}
              interval={Math.floor(data.length / 5)}
              tickFormatter={(v) => `t-${v}`}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="temp"
              domain={['auto', 'auto']}
              tick={{ fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="hum"
              orientation="right"
              domain={[50, 100]}
              tick={{ fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ stroke: '#3f424d', strokeWidth: 1, strokeDasharray: '4 4' }}
            />

            {produceConfig?.ideal_temp && (
              <ReferenceLine
                yAxisId="temp"
                y={produceConfig.ideal_temp}
                stroke="#3f424d"
                strokeDasharray="6 3"
                label={{ value: 'IDEAL', fill: '#75798c', fontSize: 9, position: 'insideTopLeft' }}
              />
            )}

            <Line
              yAxisId="temp"
              type="monotone"
              dataKey="temperature"
              name="Temperature"
              stroke="#F87171"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: '#F87171', strokeWidth: 0 }}
              isAnimationActive={false}
            />
            <Line
              yAxisId="hum"
              type="monotone"
              dataKey="humidity"
              name="Humidity"
              stroke="#4FB6C9"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: '#4FB6C9', strokeWidth: 0 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
