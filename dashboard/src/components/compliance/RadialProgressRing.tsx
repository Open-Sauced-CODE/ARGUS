import React from 'react';

interface RadialProgressRingProps {
  ruleId: string;
  name: string;
  percentage: number;
  failingCount: number;
  isSelected: boolean;
  onSelect: (ruleId: string) => void;
}

export const RadialProgressRing: React.FC<RadialProgressRingProps> = ({
  ruleId,
  name,
  percentage,
  failingCount,
  isSelected,
  onSelect,
}) => {
  // Determine color based on requirements:
  // 85 or more: verdigris (#2E9C82)
  // 70 to 84: saffron (#E2992A)
  // below 70: garnet (#BE3144)
  const strokeColor =
    percentage >= 85 ? '#2E9C82' : percentage >= 70 ? '#E2992A' : '#BE3144';

  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percentage / 100) * circumference;

  return (
    <button
      type="button"
      onClick={() => onSelect(ruleId)}
      className={`group flex flex-col items-center text-center p-3 sm:p-4 rounded-control transition-all focus:outline-none focus:ring-2 focus:ring-peacock/40 ${
        isSelected
          ? 'bg-ink-border/30 ring-1 ring-peacock/30'
          : 'hover:bg-ink-border/20'
      }`}
      aria-label={`${name}: ${percentage}% compliance, ${failingCount} failing`}
      aria-pressed={isSelected}
    >
      {/* SVG Radial Ring */}
      <div className="relative w-20 h-20 sm:w-22 sm:h-22 flex items-center justify-center">
        <svg
          viewBox="0 0 100 100"
          className="w-full h-full transform -rotate-90 select-none"
        >
          {/* Background Track */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="#D3DDD9"
            strokeWidth="7"
          />
          {/* Progress Arc */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={strokeColor}
            strokeWidth="7"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-300"
          />
        </svg>

        {/* Center Percentage */}
        <span className="absolute font-sans font-semibold text-lg sm:text-xl text-ink tabular-nums">
          {percentage}%
        </span>
      </div>

      {/* Label and Status */}
      <div className="mt-2 space-y-0.5">
        <p className="font-medium text-[13.5px] text-ink group-hover:text-peacock transition-colors">
          {name}
        </p>
        <p className="text-[12px] text-ink-muted">
          {failingCount > 0 ? `${failingCount} failing` : 'No violations'}
        </p>
      </div>
    </button>
  );
};

