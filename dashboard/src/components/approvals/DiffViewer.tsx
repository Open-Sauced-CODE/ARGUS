import React from 'react';

interface DiffViewerProps {
  diff?: {
    before: string;
    after: string;
  };
  isEscalated?: boolean;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({ diff, isEscalated }) => {
  if (isEscalated || !diff) {
    return (
      <div className="py-4 px-3 bg-mist/50 border border-ink-border/60 rounded-control text-[13px] text-ink-muted">
        <p>Diff unavailable: this finding requires human architectural review and does not produce an automated synthetic patch.</p>
      </div>
    );
  }

  const beforeLines = diff.before.split('\n');
  const afterLines = diff.after.split('\n');

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[12px] font-mono text-ink-faint">
        <span>Remediation diff (Terraform / HCL)</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[12.5px] font-mono overflow-x-auto">
        {/* Left: Before (removed lines with faint garnet tint and minus marker) */}
        <div className="space-y-1">
          <div className="text-[11px] uppercase tracking-wider text-garnet font-sans font-medium px-1">
            Before (Current state)
          </div>
          <div className="bg-paper border border-ink-border/70 rounded-control p-3 space-y-1">
            {beforeLines.map((line, idx) => (
              <div
                key={`b-${idx}`}
                className="flex items-start gap-2 bg-garnet/10 text-ink px-1.5 py-0.5 rounded"
              >
                <span className="text-garnet select-none font-bold">-</span>
                <span className="break-all whitespace-pre-wrap">{line}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right: After (added lines with faint verdigris tint and plus marker) */}
        <div className="space-y-1">
          <div className="text-[11px] uppercase tracking-wider text-verdigris font-sans font-medium px-1">
            After (Proposed state)
          </div>
          <div className="bg-paper border border-ink-border/70 rounded-control p-3 space-y-1">
            {afterLines.map((line, idx) => (
              <div
                key={`a-${idx}`}
                className="flex items-start gap-2 bg-verdigris/10 text-ink px-1.5 py-0.5 rounded"
              >
                <span className="text-verdigris select-none font-bold">+</span>
                <span className="break-all whitespace-pre-wrap">{line}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
