import React from 'react';
import { iamFindings } from '../../types';
import { useNavigate } from 'react-router-dom';

interface WaitingForYouProps {
  findings: iamFindings[];
  thresholdPct?: number;
  certified?: boolean;
}

export const WaitingForYou: React.FC<WaitingForYouProps> = ({
  findings,
  thresholdPct = 95,
  certified = false,
}) => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col justify-between h-full">
      <div>
        {/* Section Header */}
        <div className="flex items-center justify-between pb-2 border-b border-ink-border">
          <h2 className="font-headline text-2xl text-ink font-medium">Waiting for you</h2>
        </div>

        {/* Column Headers */}
        <div className="flex items-center justify-between text-[13px] text-ink-faint py-2 border-b border-ink-border/60">
          <span>Finding</span>
          <span className="text-right">Confidence</span>
        </div>

        {/* Ruled List of Findings */}
        <div className="divide-y divide-ink-border/50">
          {findings.map((item) => {
            const isEscalated = item.escalated || item.confidence === 'n/a';
            const confidenceDisplay = isEscalated
              ? 'n/a'
              : `${Math.round((item.confidence as number) * 100)}%`;

            // Reason computed from data
            const reasonText = isEscalated
              ? 'Escalated for human judgement'
              : `Below the ${Math.round(item.threshold * 100)}% auto-apply threshold`;

            return (
              <div
                key={item.finding_id}
                onClick={() => navigate(`/approvals?finding=${item.finding_id}`)}
                className="py-2.5 flex items-start justify-between gap-4 group cursor-pointer hover:bg-ink-border/30 -mx-1.5 px-1.5 rounded-control transition-colors"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    navigate(`/approvals?finding=${item.finding_id}`);
                  }
                }}
              >
                {/* Left: Finding Title and Computed Reason */}
                <div className="space-y-0.5 min-w-0 pr-2">
                  <div className="text-[14px] font-medium text-ink group-hover:text-peacock transition-colors truncate">
                    {item.title}
                  </div>
                  <div className="text-[12px] text-ink-muted">
                    {reasonText}
                  </div>
                </div>

                {/* Right: Confidence right-aligned */}
                <div className="text-right flex-shrink-0 pt-0.5">
                  <span
                    className={`text-[14px] font-medium tabular-nums ${
                      isEscalated
                        ? 'text-ink-muted font-normal'
                        : 'text-ink'
                    }`}
                  >
                    {confidenceDisplay}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Small quiet line below the list */}
      <div className="pt-2.5 mt-1 border-t border-ink-border/60 flex items-center justify-between text-[12px] text-ink-muted">
        <span>Auto-apply threshold: {thresholdPct}%{!certified ? ' (provisional)' : ''}</span>
        <button
          onClick={() => navigate('/approvals')}
          className="text-peacock hover:underline font-medium text-[12px]"
        >
          View all in queue →
        </button>
      </div>
    </div>
  );
};
