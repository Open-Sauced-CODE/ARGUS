import React from 'react';
import { Lock } from 'lucide-react';

interface FooterTitleBlockProps {
  scanId: string;
  region: string;
  scannedTime: string;
  isOnDevice: boolean;
}

export const FooterTitleBlock: React.FC<FooterTitleBlockProps> = ({
  scanId,
  region,
  scannedTime,
  isOnDevice,
}) => {
  return (
    <footer className="pt-3 pb-2 border-t border-ink-border/60 text-[13px] text-ink-muted">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left side metadata */}
        <div className="flex flex-wrap items-center gap-6 tabular-nums">
          <div className="flex items-center gap-2">
            <span className="text-ink-faint">Scan ID:</span>
            <span className="font-mono text-ink text-[12px] bg-paper px-2 py-0.5 rounded border border-ink-border/50">
              {scanId}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-ink-faint">Region:</span>
            <span className="font-medium text-ink">{region}</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-ink-faint">Scanned:</span>
            <span className="font-medium text-ink">{scannedTime}</span>
          </div>
        </div>

        {/* Right side zero-data-plane privacy indicator */}
        <div className="flex items-center gap-2 text-ink bg-paper border border-ink-border/60 px-3 py-1 rounded-control">
          <Lock strokeWidth={1.5} className="w-3.5 h-3.5 text-verdigris" />
          <span className="font-medium text-[12px]">
            {isOnDevice ? 'Processed on this device' : 'Remote verification'}
          </span>
        </div>
      </div>
    </footer>
  );
};
