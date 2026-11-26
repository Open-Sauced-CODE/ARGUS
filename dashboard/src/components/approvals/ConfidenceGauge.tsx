import React from 'react';

interface ConfidenceGaugeProps {
  confidence: number | null | 'n/a';
  threshold?: number;
  escalated?: boolean;
}

export const ConfidenceGauge: React.FC<ConfidenceGaugeProps> = ({
  confidence,
  threshold = 0.95,
  escalated = false,
}) => {
  if (escalated) {
    return (
      <div className="py-2 space-y-1">
        <p className="text-[12px] uppercase font-mono text-ink-faint">Conformal gate</p>
        <p className="text-[14px] font-medium text-ink">
          Escalated to a reviewer
        </p>
        <p className="text-[12px] text-ink-muted">
          Manual architectural verification required before policy application.
        </p>
      </div>
    );
  }

  if (confidence === null || confidence === 'n/a') {
    return (
      <div className="py-2 space-y-1">
        <p className="text-[12px] uppercase font-mono text-ink-faint">M2 Conformal Gate</p>
        <p className="text-[14px] font-medium text-ink">
          Awaiting M2 calibration — Human review required
        </p>
        <p className="text-[12px] text-ink-muted">
          Threshold: &tau;* = pending (<code className="font-mono">certified: false</code>). Autonomy remains OFF until calibrated.
        </p>
      </div>
    );
  }

  const pVal = Math.min(1, Math.max(0, confidence as number));
  const pPct = Math.round(pVal * 100);
  const thresholdPct = Math.round(threshold * 100);
  const isApproved = pVal >= threshold;

  // Semicircle geometry
  // Radius = 44, cx = 60, cy = 55. Arc path from (16, 55) to (104, 55).
  // Arc length = PI * 44 = 138.23
  const radius = 44;
  const arcLength = Math.PI * radius; // ~138.23
  const fillLength = pVal * arcLength;

  // Threshold tick coordinates: angle from PI (180deg) to 0 (0deg)
  // angle theta = PI * (1 - threshold)
  const theta = Math.PI * (1 - threshold);
  const tickInnerR = radius - 6;
  const tickOuterR = radius + 6;
  const x1 = 60 + tickInnerR * Math.cos(theta);
  const y1 = 55 - tickInnerR * Math.sin(theta);
  const x2 = 60 + tickOuterR * Math.cos(theta);
  const y2 = 55 - tickOuterR * Math.sin(theta);

  // Color: verdigris (#2E9C82) if at or above threshold, saffron (#E2992A) if below
  const strokeColor = isApproved ? '#2E9C82' : '#E2992A';

  return (
    <div className="py-2 select-none">
      <div className="flex items-center gap-6">
        {/* Flat Semicircle SVG Gauge */}
        <div className="relative w-32 h-20 flex flex-col items-center justify-end">
          <svg viewBox="0 0 120 70" className="w-full h-full overflow-visible">
            {/* Background Arc */}
            <path
              d="M 16 55 A 44 44 0 0 1 104 55"
              fill="none"
              stroke="#D3DDD9"
              strokeWidth="7"
              strokeLinecap="round"
            />
            {/* Foreground Progress Arc */}
            <path
              d="M 16 55 A 44 44 0 0 1 104 55"
              fill="none"
              stroke={strokeColor}
              strokeWidth="7"
              strokeDasharray={`${fillLength} ${arcLength}`}
              strokeLinecap="round"
              className="transition-all duration-300"
            />
            {/* Threshold Tick Line */}
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="#0F2428"
              strokeWidth="1.5"
            />
          </svg>

          {/* Large Tabular Value */}
          <div className="absolute bottom-1 flex flex-col items-center">
            <span className="font-sans text-xl font-bold text-ink tabular-nums leading-none">
              {pPct}%
            </span>
            <span className="text-[10px] font-mono text-ink-faint mt-0.5">
              p-hat
            </span>
          </div>
        </div>

        {/* Labels and Threshold Info */}
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                isApproved ? 'bg-verdigris' : 'bg-saffron'
              }`}
            />
            <span
              className={`text-[13.5px] font-medium ${
                isApproved ? 'text-verdigris' : 'text-saffron'
              }`}
            >
              {isApproved ? 'Auto-apply approved' : 'Needs human approval'}
            </span>
          </div>

          <p className="text-[12px] font-mono text-ink-muted">
            Threshold: τ* = {thresholdPct}%
          </p>
          <p className="text-[11.5px] text-ink-faint">
            {isApproved
              ? 'Conformal risk prediction cleared gate.'
              : 'Residual ambiguity exceeds calibrated error rate.'}
          </p>
        </div>
      </div>
    </div>
  );
};
