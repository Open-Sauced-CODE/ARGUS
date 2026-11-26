import React from 'react';
import { iamComp } from '../../types';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, Info } from 'lucide-react';

interface ComplianceListProps {
  rules: iamComp[];
}

export const ComplianceList: React.FC<ComplianceListProps> = ({ rules }) => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col justify-between h-full">
      <div>
        {/* Section Header — without DPDP chip */}
        <div className="flex items-center justify-between pb-2 border-b border-ink-border">
          <h2 className="font-headline text-2xl text-ink font-medium">Compliance</h2>
        </div>

        {/* List of Rules */}
        <div className="divide-y divide-ink-border/50">
          {rules.map((rule) => {
            const isVisibility = rule.is_visibility_flag;
            const isWarning = rule.status === 'WARNING';

            return (
              <div
                key={rule.rule_id}
                onClick={() => navigate(`/compliance?rule=${rule.rule_id}`)}
                className="py-2.5 flex items-center justify-between gap-4 group cursor-pointer hover:bg-ink-border/30 -mx-1.5 px-1.5 rounded-control transition-colors"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    navigate(`/compliance?rule=${rule.rule_id}`);
                  }
                }}
              >
                {/* Left: Rule Name and Status / Failing count */}
                <div className="flex-1 min-w-0 pr-2">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[14px] font-medium text-ink group-hover:text-peacock transition-colors truncate">
                      {rule.name}
                    </span>

                    {/* Score Percentage or Visibility Info */}
                    {!isVisibility && rule.score_pct !== undefined ? (
                      <span
                        className={`text-[14px] font-semibold tabular-nums ${
                          isWarning ? 'text-saffron' : 'text-ink'
                        }`}
                      >
                        {rule.score_pct}%
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[12px] text-lapis font-medium">
                        <Info className="w-3.5 h-3.5" strokeWidth={1.5} />
                        Visibility flag
                      </span>
                    )}
                  </div>

                  {/* Progress bar for standard rules; Info note for Rule 15 */}
                  {!isVisibility && rule.score_pct !== undefined ? (
                    <div className="space-y-0.5">
                      <div className="w-full h-1.5 bg-paper rounded-full overflow-hidden border border-ink-border/60">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${
                            isWarning ? 'bg-saffron' : 'bg-verdigris'
                          }`}
                          style={{ width: `${rule.score_pct}%` }}
                        />
                      </div>
                      <div className="text-[12px] text-ink-muted">
                        {rule.failing_count} failing
                      </div>
                    </div>
                  ) : (
                    <div className="text-[12px] text-ink-muted">
                      {rule.review_count} flagged for review
                    </div>
                  )}
                </div>

                {/* Subtle right chevron */}
                <div className="flex-shrink-0 text-ink-faint group-hover:text-ink transition-colors pl-1">
                  <ChevronRight strokeWidth={1.5} className="w-4 h-4" />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer Navigation Link */}
      <div className="pt-2.5 mt-1 border-t border-ink-border/60 flex items-center justify-between text-[12px] text-ink-muted">
        <span>India DPDP Act (2025/2027)</span>
        <button
          onClick={() => navigate('/compliance')}
          className="text-peacock hover:underline font-medium text-[12px]"
        >
          Detailed scorecard →
        </button>
      </div>
    </div>
  );
};
