import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { ParetoPoint } from '../../types';

interface FrontierChartProps {
  data: ParetoPoint[];
  selectedK: number;
}

export const FrontierChart: React.FC<FrontierChartProps> = ({ data, selectedK }) => {
  // Format data into percentage for chart
  const formattedData = data.map((pt) => ({
    budget: pt.budget,
    milp: Math.round(pt.residual * 100),
    naive: Math.round(pt.naive_residual * 100),
    stackelberg: Math.round(pt.stackelberg_residual * 100),
  }));

  const currentPt = formattedData.find((d) => d.budget === selectedK);
  const milpValue = currentPt ? currentPt.milp : 0;
  const naiveValue = currentPt ? currentPt.naive : 0;
  const diff = naiveValue - milpValue;

  return (
    <div className="flex flex-col h-full select-none">
      <div className="flex items-center justify-between pb-2 border-b border-ink-border">
        <h2 className="font-headline text-2xl text-ink font-medium">Frontier</h2>
        <span className="text-[12px] font-mono text-ink-muted">
          K={selectedK}
        </span>
      </div>

      <p className="text-[12.5px] text-ink-muted pt-2 pb-1">
        Modelled attack likelihood across budget options (K = 0 to 10). Lower is better.
      </p>

      {/* Chart container */}
      <div className="w-full h-56 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={formattedData}
            margin={{ top: 12, right: 16, left: -16, bottom: 4 }}
          >
            <XAxis
              dataKey="budget"
              stroke="#879B9E"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: '#D3DDD9' }}
              domain={[0, 10]}
              type="number"
              ticks={[0, 2, 4, 6, 8, 10]}
            />
            <YAxis
              stroke="#879B9E"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: '#D3DDD9' }}
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              unit="%"
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload || !payload.length) return null;
                return (
                  <div className="bg-paper border border-ink-border rounded-control p-2.5 shadow-soft text-[12px] space-y-1">
                    <p className="font-mono text-ink font-medium">Budget K = {label}</p>
                    <div className="space-y-0.5">
                      <p className="text-peacock font-medium">
                        Interdiction MILP: {payload[0]?.value}%
                      </p>
                      <p className="text-lapis">
                        Stackelberg game: {payload[1]?.value}%
                      </p>
                      <p className="text-ink-faint">
                        Naive top-K: {payload[2]?.value}%
                      </p>
                    </div>
                  </div>
                );
              }}
            />
            <ReferenceLine
              x={selectedK}
              stroke="#4A6266"
              strokeDasharray="3 3"
              strokeWidth={1.5}
            />
            {/* 1. MILP (best, heaviest, peacock) */}
            <Line
              type="monotone"
              dataKey="milp"
              name="Interdiction MILP"
              stroke="#0A2E33"
              strokeWidth={2.4}
              dot={false}
              activeDot={{ r: 4, fill: '#0A2E33', stroke: '#F9FAF8', strokeWidth: 1.5 }}
              isAnimationActive={false}
            />
            {/* 2. Stackelberg game (lapis) */}
            <Line
              type="monotone"
              dataKey="stackelberg"
              name="Stackelberg game"
              stroke="#4C6EA8"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
            />
            {/* 3. Naive top-K (ink-faint) */}
            <Line
              type="monotone"
              dataKey="naive"
              name="Naive top-K by PageRank"
              stroke="#879B9E"
              strokeWidth={1.5}
              strokeDasharray="2 2"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="pt-2 flex flex-wrap items-center gap-4 text-[12px] text-ink-muted">
        <div className="flex items-center gap-1.5">
          <span className="w-3.5 h-0.5 bg-peacock inline-block" />
          <span className="font-medium text-ink">Interdiction MILP</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3.5 h-0.5 bg-lapis inline-block" />
          <span>Stackelberg game</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3.5 h-0.5 bg-ink-faint inline-block" />
          <span>Naive top-K</span>
        </div>
      </div>

      {/* Caption comparing MILP vs Naive */}
      <div className="pt-2 mt-auto border-t border-ink-border/50 text-[12px] text-ink-muted flex items-center justify-between">
        {formattedData.length === 0 ? (
          <span>No multi-hop IAM attack paths to Crown Jewels (0% graph exposure).</span>
        ) : (
          <span>
            At K={selectedK}, MILP residual likelihood is{' '}
            <strong className="text-ink font-semibold font-tabular">
              {diff > 0 ? `${diff} percentage points lower` : 'equal to'}
            </strong>{' '}
            than naive prioritization ({milpValue}% vs {naiveValue}%).
          </span>
        )}
      </div>
    </div>
  );
};

