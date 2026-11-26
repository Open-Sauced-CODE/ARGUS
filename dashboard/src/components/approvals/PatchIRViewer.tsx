import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Layers } from 'lucide-react';

interface PatchIRViewerProps {
  patchIr?: {
    finding_id: string;
    resource_ref: string;
    ops: Array<{
      op: string;
      attr?: string;
      value?: any;
      [key: string]: any;
    }>;
    rationale_ref: string;
  };
}

export const PatchIRViewer: React.FC<PatchIRViewerProps> = ({ patchIr }) => {
  const [isOpen, setIsOpen] = useState(false);

  if (!patchIr) return null;

  const opNames = Array.from(new Set(patchIr.ops.map((o) => o.op)));

  return (
    <div className="border border-ink-border/60 rounded-control bg-paper/60 overflow-hidden">
      {/* Header and Op badges */}
      <div className="p-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-ink-faint flex-shrink-0" />
          <span className="text-[13px] font-medium text-ink">Patch-IR operations</span>
          <div className="flex items-center gap-1.5 flex-wrap">
            {opNames.map((op) => (
              <span
                key={op}
                className="font-mono text-[11px] bg-ink-border/40 text-peacock px-2 py-0.5 rounded"
              >
                {op}
              </span>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="inline-flex items-center gap-1 text-[12px] font-mono text-peacock hover:underline focus:outline-none focus:ring-1 focus:ring-peacock/40 rounded px-1"
          aria-expanded={isOpen}
        >
          <span>{isOpen ? 'Collapse JSON' : 'Inspect JSON'}</span>
          {isOpen ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      {/* Collapsible raw JSON */}
      {isOpen && (
        <div className="border-t border-ink-border/50 bg-paper p-3 text-[11.5px] font-mono text-ink overflow-x-auto">
          <pre className="whitespace-pre-wrap">
            {JSON.stringify(patchIr, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};
