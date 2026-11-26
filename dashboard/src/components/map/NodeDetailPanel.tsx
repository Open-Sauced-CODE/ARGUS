import React from 'react';
import { iamNodes, iamEdges, NodeKind, EdgeType } from '../../types';
import { X, AlertTriangle, Shield, KeyRound, Database, FileText, User } from 'lucide-react';

// ---- Risk helpers ----
function riskColor(risk: number): string {
  if (risk >= 90) return '#BE3144';
  if (risk >= 70) return '#E2992A';
  return '#2E9C82';
}
function riskLabel(risk: number): string {
  if (risk >= 90) return 'Critical';
  if (risk >= 70) return 'High';
  if (risk >= 40) return 'Medium';
  return 'Low';
}

// ---- Kind display ----
const KIND_LABELS: Record<NodeKind, string> = {
  user:   'IAM user',
  role:   'IAM role',
  key:    'Access key',
  sg:     'Security group',
  bucket: 'S3 bucket',
  stmt:   'Policy statement',
  admin:  'Admin identity',
};

const KindIcon: React.FC<{ kind: NodeKind; className?: string }> = ({ kind, className = 'w-4 h-4' }) => {
  const props = { strokeWidth: 1.5, className };
  switch (kind) {
    case 'user':   return <User {...props} />;
    case 'role':   return <Shield {...props} />;
    case 'key':    return <KeyRound {...props} />;
    case 'sg':     return <Shield {...props} />;
    case 'bucket': return <Database {...props} />;
    case 'stmt':   return <FileText {...props} />;
    default:       return <AlertTriangle {...props} />;
  }
};

// ---- Edge type labels ----
const ETYPE_LABELS: Record<EdgeType, string> = {
  CAN_ESCALATE: 'Can escalate',
  DIRECT_ADMIN: 'Direct admin',
  CAN_ACCESS:   'Can access',
  RULE_TO_SG:   'Rule → security group',
  USES_KEY:     'Uses key',
  CAN_ASSUME:   'Can assume role',
};

interface NodeDetailPanelProps {
  node: iamNodes;
  allEdges: iamEdges[];
  allNodes: iamNodes[];
  onClose: () => void;
  onSelectNode: (id: string) => void;
}

export const NodeDetailPanel: React.FC<NodeDetailPanelProps> = ({
  node,
  allEdges,
  allNodes,
  onClose,
  onSelectNode,
}) => {
  const nodeMap = React.useMemo(() => {
    const m = new Map<string, iamNodes>();
    allNodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [allNodes]);

  const incoming = allEdges.filter((e) => e.target === node.id);
  const outgoing = allEdges.filter((e) => e.source === node.id);

  const rc = riskColor(node.risk);

  return (
    <aside
      className="absolute right-4 top-4 bottom-4 w-72 rounded-panel bg-peacock-dark/90 border border-contour/60 shadow-soft text-paper flex flex-col overflow-hidden z-20"
      role="complementary"
      aria-label={`Node detail: ${node.label}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between px-4 py-3 border-b border-contour/50">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-paper/60 flex-shrink-0">
            <KindIcon kind={node.kind} className="w-4 h-4" />
          </span>
          <div className="min-w-0">
            <p className="font-medium text-[14px] truncate text-paper">{node.label}</p>
            <p className="text-[11px] text-paper/50 mt-0.5">
              {KIND_LABELS[node.kind] ?? node.kind}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close node detail panel"
          className="text-paper/50 hover:text-paper transition-colors flex-shrink-0 ml-2 mt-0.5"
        >
          <X strokeWidth={1.5} className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 text-[13px]">
        {/* Badges */}
        <div className="flex flex-wrap gap-1.5">
          {node.isEntry && (
            <span className="px-2 py-0.5 rounded-control text-[11px] font-medium border border-garnet/60 text-garnet bg-garnet/10">
              Entry point
            </span>
          )}
          {node.isCrownJewel && (
            <span className="px-2 py-0.5 rounded-control text-[11px] font-medium border border-brass/60 text-brass bg-brass/10">
              Crown jewel
            </span>
          )}
        </div>

        {/* Risk score */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-paper/70">Risk score</span>
            <span className="font-tabular font-semibold" style={{ color: rc }}>
              {node.risk} / 100
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-contour/40 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${node.risk}%`, background: rc }}
            />
          </div>
          <p className="text-[11px] mt-1" style={{ color: rc }}>
            {riskLabel(node.risk)}
          </p>
        </div>

        {/* ARN / ID */}
        <div>
          <p className="text-paper/60 text-[11px] mb-1">Resource ID</p>
          <p className="font-mono text-[11px] text-paper/80 break-all leading-relaxed">{node.id}</p>
        </div>

        {/* Incoming edges */}
        {incoming.length > 0 && (
          <div>
            <p className="text-paper/60 text-[11px] mb-2">
              Incoming edges ({incoming.length})
            </p>
            <div className="space-y-1.5">
              {incoming.map((e) => {
                const src = nodeMap.get(e.source);
                return (
                  <button
                    key={e.source + '->' + e.target}
                    type="button"
                    onClick={() => onSelectNode(e.source)}
                    className="w-full text-left flex items-start gap-2 p-2 rounded-control hover:bg-contour/30 transition-colors group"
                  >
                    <span className="text-paper/40 mt-0.5 flex-shrink-0">←</span>
                    <div className="min-w-0">
                      <p className="text-paper group-hover:text-paper/90 truncate text-[12px] font-medium">
                        {src?.label ?? e.source}
                      </p>
                      <p className="text-paper/50 text-[11px]">
                        {ETYPE_LABELS[e.etype] ?? e.etype}
                        <span className="ml-1.5 font-mono">p={e.p.toFixed(2)}</span>
                      </p>
                    </div>
                    {e.isAttackPath && (
                      <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-garnet mt-1" title="Attack path" />
                    )}
                    {e.isInterdicted && (
                      <span className="flex-shrink-0 text-[10px] text-garnet mt-0.5" title="Interdicted">✂</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Outgoing edges */}
        {outgoing.length > 0 && (
          <div>
            <p className="text-paper/60 text-[11px] mb-2">
              Outgoing edges ({outgoing.length})
            </p>
            <div className="space-y-1.5">
              {outgoing.map((e) => {
                const tgt = nodeMap.get(e.target);
                return (
                  <button
                    key={e.source + '->' + e.target}
                    type="button"
                    onClick={() => onSelectNode(e.target)}
                    className="w-full text-left flex items-start gap-2 p-2 rounded-control hover:bg-contour/30 transition-colors group"
                  >
                    <span className="text-paper/40 mt-0.5 flex-shrink-0">→</span>
                    <div className="min-w-0">
                      <p className="text-paper group-hover:text-paper/90 truncate text-[12px] font-medium">
                        {tgt?.label ?? e.target}
                      </p>
                      <p className="text-paper/50 text-[11px]">
                        {ETYPE_LABELS[e.etype] ?? e.etype}
                        <span className="ml-1.5 font-mono">p={e.p.toFixed(2)}</span>
                      </p>
                    </div>
                    {e.isAttackPath && (
                      <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-garnet mt-1" title="Attack path" />
                    )}
                    {e.isInterdicted && (
                      <span className="flex-shrink-0 text-[10px] text-garnet mt-0.5" title="Interdicted">✂</span>
                    )}
                    {e.residual && (
                      <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full mt-1" style={{ background: '#52B2A0' }} title="Residual path" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-contour/40 text-[11px] text-paper/40 font-mono">
        {incoming.length} in · {outgoing.length} out
      </div>
    </aside>
  );
};

