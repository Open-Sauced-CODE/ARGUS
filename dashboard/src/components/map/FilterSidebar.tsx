import React from 'react';
import { NodeKind, EdgeType } from '../../types';
import { Filter, ChevronDown } from 'lucide-react';

// ---- Kind display config (extensible, neutral fallback) ----
const KIND_CONFIG: Record<string, { label: string; color: string }> = {
  user:   { label: 'IAM user',    color: '#F9FAF8' },
  role:   { label: 'IAM role',    color: '#4C6EA8' },
  key:    { label: 'Access key',  color: '#2E9C82' },
  sg:     { label: 'Security group', color: '#E2992A' },
  bucket: { label: 'S3 bucket',  color: '#B58A3C' },
  stmt:   { label: 'Policy stmt', color: '#BE3144' },
  admin:  { label: 'Admin',       color: '#BE3144' },
};
const KIND_FALLBACK_COLOR = '#1B5058';

// ---- Edge type display config ----
const ETYPE_CONFIG: Record<string, { label: string }> = {
  CAN_ESCALATE:  { label: 'Can escalate' },
  DIRECT_ADMIN:  { label: 'Direct admin' },
  CAN_ACCESS:    { label: 'Can access' },
  RULE_TO_SG:    { label: 'Rule → SG' },
  USES_KEY:      { label: 'Uses key' },
  CAN_ASSUME:    { label: 'Can assume' },
};

interface FilterSidebarProps {
  allKinds: NodeKind[];
  allEtypes: EdgeType[];
  visibleKinds: Set<NodeKind>;
  visibleEtypes: Set<EdgeType>;
  showAttackPath: boolean;
  showResidual: boolean;
  onToggleKind: (kind: NodeKind) => void;
  onToggleEtype: (etype: EdgeType) => void;
  onToggleAttackPath: () => void;
  onToggleResidual: () => void;
  onReset: () => void;
}

export const FilterSidebar: React.FC<FilterSidebarProps> = ({
  allKinds,
  allEtypes,
  visibleKinds,
  visibleEtypes,
  showAttackPath,
  showResidual,
  onToggleKind,
  onToggleEtype,
  onToggleAttackPath,
  onToggleResidual,
  onReset,
}) => {
  const [kindsOpen, setKindsOpen] = React.useState(true);
  const [etypesOpen, setEtypesOpen] = React.useState(true);
  const [pathsOpen, setPathsOpen] = React.useState(true);

  const allKindsSelected = allKinds.every((k) => visibleKinds.has(k));
  const allEtypesSelected = allEtypes.every((e) => visibleEtypes.has(e));
  const isDirty = !allKindsSelected || !allEtypesSelected || !showAttackPath || !showResidual;

  return (
    <aside
      className="absolute left-4 top-4 bottom-4 w-56 rounded-panel bg-peacock-dark/90 border border-contour/60 shadow-soft text-paper text-[13px] flex flex-col overflow-hidden z-20"
      aria-label="Graph filters"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-contour/50">
        <div className="flex items-center gap-2 font-medium">
          <Filter strokeWidth={1.5} className="w-3.5 h-3.5 text-paper/70" />
          <span>Filters</span>
        </div>
        {isDirty && (
          <button
            type="button"
            onClick={onReset}
            className="text-[11px] text-saffron hover:text-saffron/80 transition-colors"
          >
            Reset
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* ---- Node kinds ---- */}
        <div className="border-b border-contour/30">
          <button
            type="button"
            className="w-full flex items-center justify-between px-4 py-2.5 text-paper/80 hover:text-paper transition-colors"
            onClick={() => setKindsOpen((o) => !o)}
            aria-expanded={kindsOpen}
          >
            <span className="font-medium text-[12px] uppercase tracking-wide text-paper/60">
              Node kinds
            </span>
            <ChevronDown
              strokeWidth={1.5}
              className={`w-3.5 h-3.5 transition-transform ${kindsOpen ? 'rotate-180' : ''}`}
            />
          </button>
          {kindsOpen && (
            <div className="px-4 pb-3 space-y-2">
              {allKinds.map((kind) => {
                const cfg = KIND_CONFIG[kind] ?? { label: kind, color: KIND_FALLBACK_COLOR };
                const checked = visibleKinds.has(kind);
                return (
                  <label
                    key={kind}
                    className="flex items-center gap-2.5 cursor-pointer group"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggleKind(kind)}
                      className="sr-only"
                    />
                    {/* Custom checkbox */}
                    <span
                      className="w-3.5 h-3.5 rounded-sm border flex items-center justify-center flex-shrink-0 transition-colors"
                      style={{
                        borderColor: checked ? cfg.color : 'rgba(249,250,248,0.3)',
                        background: checked ? cfg.color + '33' : 'transparent',
                      }}
                    >
                      {checked && (
                        <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                          <path d="M1 3l2 2 4-4" stroke={cfg.color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    {/* Swatch */}
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: cfg.color }}
                    />
                    <span className={`transition-colors ${checked ? 'text-paper' : 'text-paper/50'}`}>
                      {cfg.label}
                    </span>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        {/* ---- Edge types ---- */}
        <div className="border-b border-contour/30">
          <button
            type="button"
            className="w-full flex items-center justify-between px-4 py-2.5 text-paper/80 hover:text-paper transition-colors"
            onClick={() => setEtypesOpen((o) => !o)}
            aria-expanded={etypesOpen}
          >
            <span className="font-medium text-[12px] uppercase tracking-wide text-paper/60">
              Edge types
            </span>
            <ChevronDown
              strokeWidth={1.5}
              className={`w-3.5 h-3.5 transition-transform ${etypesOpen ? 'rotate-180' : ''}`}
            />
          </button>
          {etypesOpen && (
            <div className="px-4 pb-3 space-y-2">
              {allEtypes.map((etype) => {
                const cfg = ETYPE_CONFIG[etype] ?? { label: etype };
                const checked = visibleEtypes.has(etype);
                return (
                  <label key={etype} className="flex items-center gap-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggleEtype(etype)}
                      className="sr-only"
                    />
                    <span
                      className="w-3.5 h-3.5 rounded-sm border flex items-center justify-center flex-shrink-0 transition-colors"
                      style={{
                        borderColor: checked ? 'rgba(249,250,248,0.7)' : 'rgba(249,250,248,0.3)',
                        background: checked ? 'rgba(249,250,248,0.1)' : 'transparent',
                      }}
                    >
                      {checked && (
                        <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                          <path d="M1 3l2 2 4-4" stroke="#F9FAF8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    <span className={`transition-colors ${checked ? 'text-paper' : 'text-paper/50'}`}>
                      {cfg.label}
                    </span>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        {/* ---- Paths ---- */}
        <div>
          <button
            type="button"
            className="w-full flex items-center justify-between px-4 py-2.5 text-paper/80 hover:text-paper transition-colors"
            onClick={() => setPathsOpen((o) => !o)}
            aria-expanded={pathsOpen}
          >
            <span className="font-medium text-[12px] uppercase tracking-wide text-paper/60">
              Paths
            </span>
            <ChevronDown
              strokeWidth={1.5}
              className={`w-3.5 h-3.5 transition-transform ${pathsOpen ? 'rotate-180' : ''}`}
            />
          </button>
          {pathsOpen && (
            <div className="px-4 pb-3 space-y-2">
              {/* Attack path toggle */}
              <label className="flex items-center gap-2.5 cursor-pointer">
                <input type="checkbox" checked={showAttackPath} onChange={onToggleAttackPath} className="sr-only" />
                <span
                  className="w-3.5 h-3.5 rounded-sm border flex items-center justify-center flex-shrink-0 transition-colors"
                  style={{
                    borderColor: showAttackPath ? '#BE3144' : 'rgba(249,250,248,0.3)',
                    background: showAttackPath ? '#BE314433' : 'transparent',
                  }}
                >
                  {showAttackPath && (
                    <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                      <path d="M1 3l2 2 4-4" stroke="#BE3144" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className="w-4 h-0.5 bg-garnet flex-shrink-0 rounded" />
                <span className={showAttackPath ? 'text-paper' : 'text-paper/50'}>Attack path</span>
              </label>

              {/* Residual path toggle */}
              <label className="flex items-center gap-2.5 cursor-pointer">
                <input type="checkbox" checked={showResidual} onChange={onToggleResidual} className="sr-only" />
                <span
                  className="w-3.5 h-3.5 rounded-sm border flex items-center justify-center flex-shrink-0 transition-colors"
                  style={{
                    borderColor: showResidual ? '#52B2A0' : 'rgba(249,250,248,0.3)',
                    background: showResidual ? '#52B2A033' : 'transparent',
                  }}
                >
                  {showResidual && (
                    <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                      <path d="M1 3l2 2 4-4" stroke="#52B2A0" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className="w-4 h-0.5 flex-shrink-0 rounded" style={{ background: '#52B2A0' }} />
                <span className={showResidual ? 'text-paper' : 'text-paper/50'}>Residual path</span>
              </label>
            </div>
          )}
        </div>
      </div>

      {/* Footer: node count */}
      <div className="px-4 py-2.5 border-t border-contour/40 text-[11px] text-paper/50 font-mono">
        {allKinds.length} kinds · {allEtypes.length} edge types
      </div>
    </aside>
  );
};

