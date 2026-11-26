import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getInitialGraph, getInitialInterdiction, getInterdiction, getGraph } from '../api';
import { iamNodes, iamEdges, iamRem, NodeKind, EdgeType, GraphPayload } from '../types';
import { useBudgetStore } from '../store/budgetStore';
import { useWorkspaceStore } from '../store/workspaceStore';
import { AttackGraphCanvas } from '../components/graph/AttackGraphCanvas';
import { FilterSidebar } from '../components/map/FilterSidebar';
import { NodeDetailPanel } from '../components/map/NodeDetailPanel';
import { GitFork, Activity } from 'lucide-react';

// ---- Shortest path via BFS through directed edges ----
function bfsShortestPath(
  _nodes: iamNodes[],
  edges: iamEdges[],
  fromId: string,
  toId: string
): Set<string> | null {
  if (fromId === toId) return new Set([fromId]);

  const adj = new Map<string, string[]>();
  edges.forEach((e) => {
    if (!adj.has(e.source)) adj.set(e.source, []);
    adj.get(e.source)!.push(e.target);
  });

  const visited = new Set<string>();
  const prev = new Map<string, string>();
  const queue: string[] = [fromId];
  visited.add(fromId);

  while (queue.length > 0) {
    const cur = queue.shift()!;
    const neighbors = adj.get(cur) ?? [];
    for (const nb of neighbors) {
      if (!visited.has(nb)) {
        visited.add(nb);
        prev.set(nb, cur);
        if (nb === toId) {
          // Reconstruct path
          const path = new Set<string>();
          let c: string | undefined = toId;
          while (c !== undefined) {
            path.add(c);
            c = prev.get(c);
          }
          return path;
        }
        queue.push(nb);
      }
    }
  }
  return null; // no path
}

// ---- Stats bar above the canvas ----
interface StatsBarProps {
  nodes: iamNodes[];
  edges: iamEdges[];
  interdiction: iamRem;
  shortestPathLength: number | null;
}
const StatsBar: React.FC<StatsBarProps> = ({ nodes, edges, interdiction, shortestPathLength }) => {
  const attackNodes = useMemo(() => {
    const attackEdges = edges.filter((e) => e.isAttackPath);
    const ids = new Set<string>();
    attackEdges.forEach((e) => { ids.add(e.source); ids.add(e.target); });
    return ids.size;
  }, [edges]);

  const interdictedEdgeCount = edges.filter((e) => e.isInterdicted).length;

  return (
    <div className="h-10 border-b border-ink-border/40 bg-peacock/95 px-4 flex items-center gap-6 text-[12px] font-tabular text-paper/80 flex-shrink-0">
      <div className="flex items-center gap-1.5">
        <Activity strokeWidth={1.5} className="w-3.5 h-3.5 text-paper/50" />
        <span className="text-paper/50">Graph</span>
        <span className="font-medium text-paper">{nodes.length} nodes</span>
        <span className="text-paper/30">·</span>
        <span className="font-medium text-paper">{edges.length} edges</span>
      </div>
      <div className="w-px h-4 bg-contour/60" />
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-0.5 bg-garnet inline-block rounded" />
        <span>{attackNodes} on attack path</span>
        <span className="text-paper/30 ml-1">·</span>
        <span className="text-[10px] text-garnet ml-0.5">✂ {interdictedEdgeCount} cut</span>
      </div>
      <div className="w-px h-4 bg-contour/60" />
      <div className="flex items-center gap-1.5">
        <span className="text-paper/50">Residual likelihood</span>
        <span
          className="font-semibold"
          style={{ color: interdiction.residual_likelihood > 0.8 ? '#BE3144' : interdiction.residual_likelihood > 0.6 ? '#E2992A' : '#2E9C82' }}
        >
          {(interdiction.residual_likelihood * 100).toFixed(1)}%
        </span>
        <span className="text-paper/30">(budget K={interdiction.budget})</span>
      </div>
      {shortestPathLength !== null && (
        <>
          <div className="w-px h-4 bg-contour/60" />
          <div className="flex items-center gap-1.5">
            <GitFork strokeWidth={1.5} className="w-3.5 h-3.5 text-lapis" />
            <span className="text-lapis font-medium">Shortest path: {shortestPathLength} hops</span>
          </div>
        </>
      )}
    </div>
  );
};

// ============================================================
export const MapPage: React.FC = () => {
  // Shared budget K & workspace state
  const { k } = useBudgetStore();
  const { runtimeTarget, workspaceRevision } = useWorkspaceStore();

  // Data: initialized with fallback, synced with live backend graph
  const [graphData, setGraphData] = useState<GraphPayload>(() => getInitialGraph());
  const [interdiction, setInterdiction] = useState<iamRem>(() => getInitialInterdiction(k));

  // Sync live attack graph from backend on mount or runtime/scan updates
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const liveGraph = await getGraph();
        if (mounted && liveGraph && Array.isArray(liveGraph.nodes)) {
          setGraphData(liveGraph);
        }
      } catch (err) {
        console.warn('Failed to load live graph from backend:', err);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [runtimeTarget, workspaceRevision]);

  // Sync interdiction data when shared budget K or runtime/scan updates
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await getInterdiction(k);
        if (mounted) setInterdiction(res);
      } catch (err) {
        console.warn('Failed to refresh interdiction for budget K in map:', err);
      }
    })();
    return () => { mounted = false; };
  }, [k, runtimeTarget, workspaceRevision]);

  const allNodes: iamNodes[] = graphData.nodes as iamNodes[];

  // Update edges dynamically to mark interdicted cuts according to shared K
  const allEdges: iamEdges[] = useMemo(() => {
    const cutSet = new Set(
      (interdiction.edges_interdicted || []).map((e) => `${e.source}->${e.target}`)
    );
    return (graphData.edges as iamEdges[]).map((e) => {
      const isCut = cutSet.has(`${e.source}->${e.target}`);
      return {
        ...e,
        isInterdicted: isCut,
      };
    });
  }, [graphData.edges, interdiction.edges_interdicted]);

  // Derive all distinct kinds and etypes from data
  const allKinds = useMemo<NodeKind[]>(() => {
    const kinds = new Set<NodeKind>();
    allNodes.forEach((n) => kinds.add(n.kind));
    return Array.from(kinds);
  }, [allNodes]);

  const allEtypes = useMemo<EdgeType[]>(() => {
    const etypes = new Set<EdgeType>();
    allEdges.forEach((e) => etypes.add(e.etype));
    return Array.from(etypes);
  }, [allEdges]);

  // Filter state
  const [visibleKinds, setVisibleKinds] = useState<Set<NodeKind>>(() => new Set(allKinds));
  const [visibleEtypes, setVisibleEtypes] = useState<Set<EdgeType>>(() => new Set(allEtypes));
  const [showAttackPath, setShowAttackPath] = useState(true);
  const [showResidual, setShowResidual] = useState(true);

  // Keep filter sets in sync when allKinds/allEtypes change
  useEffect(() => { setVisibleKinds(new Set(allKinds)); }, [allKinds]);
  useEffect(() => { setVisibleEtypes(new Set(allEtypes)); }, [allEtypes]);

  // Selection state with searchParams
  const [searchParams, setSearchParams] = useSearchParams();
  const initialParam = searchParams.get('node');
  const [selectedId, setSelectedId] = useState<string | null>(initialParam);

  const selectedNode = useMemo(
    () => allNodes.find((n) => n.id === selectedId) ?? null,
    [allNodes, selectedId]
  );

  // Shortest-path highlight: from entry → crown jewel (or to/from selected node)
  const entryNode = useMemo(() => allNodes.find((n) => n.isEntry), [allNodes]);
  const crownJewelNode = useMemo(() => allNodes.find((n) => n.isCrownJewel), [allNodes]);

  const [shortestPathHighlight, setShortestPathHighlight] = useState(false);

  const highlightNodeIds = useMemo<Set<string> | undefined>(() => {
    if (!shortestPathHighlight || !entryNode || !crownJewelNode) return undefined;
    const fromId = selectedId && selectedId !== crownJewelNode.id ? selectedId : entryNode.id;
    const toId = crownJewelNode.id;
    return bfsShortestPath(allNodes, allEdges, fromId, toId) ?? undefined;
  }, [shortestPathHighlight, selectedId, entryNode, crownJewelNode, allNodes, allEdges]);

  const shortestPathLength = highlightNodeIds ? highlightNodeIds.size - 1 : null;

  // Handlers
  const handleToggleKind = useCallback((kind: NodeKind) => {
    setVisibleKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }, []);

  const handleToggleEtype = useCallback((etype: EdgeType) => {
    setVisibleEtypes((prev) => {
      const next = new Set(prev);
      if (next.has(etype)) next.delete(etype);
      else next.add(etype);
      return next;
    });
  }, []);

  const handleResetFilters = useCallback(() => {
    setVisibleKinds(new Set(allKinds));
    setVisibleEtypes(new Set(allEtypes));
    setShowAttackPath(true);
    setShowResidual(true);
  }, [allKinds, allEtypes]);

  const handleSelect = useCallback((id: string | null) => {
    setSelectedId(id);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id) {
          next.set('node', id);
        } else {
          next.delete('node');
        }
        return next;
      },
      { replace: true }
    );
  }, [setSearchParams]);

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Stats bar */}
      <StatsBar
        nodes={allNodes}
        edges={allEdges}
        interdiction={interdiction}
        shortestPathLength={shortestPathLength}
      />

      {/* Canvas area — full bleed, fills remaining height */}
      <div className="relative flex-1 min-h-0 overflow-hidden bg-peacock">
        {/* The graph canvas — full width and height */}
        <AttackGraphCanvas
          nodes={allNodes}
          edges={allEdges}
          interdiction={interdiction}
          selectedId={selectedId}
          onSelect={handleSelect}
          compact={false}
          className="absolute inset-0 rounded-none"
          height={undefined as unknown as number}
          visibleKinds={visibleKinds}
          visibleEtypes={visibleEtypes}
          showAttackPath={showAttackPath}
          showResidual={showResidual}
          highlightNodeIds={highlightNodeIds}
        />

        {/* Filter sidebar — floating left */}
        <FilterSidebar
          allKinds={allKinds}
          allEtypes={allEtypes}
          visibleKinds={visibleKinds}
          visibleEtypes={visibleEtypes}
          showAttackPath={showAttackPath}
          showResidual={showResidual}
          onToggleKind={handleToggleKind}
          onToggleEtype={handleToggleEtype}
          onToggleAttackPath={() => setShowAttackPath((v) => !v)}
          onToggleResidual={() => setShowResidual((v) => !v)}
          onReset={handleResetFilters}
        />

        {/* Node detail panel — floating right */}
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            allEdges={allEdges}
            allNodes={allNodes}
            onClose={() => setSelectedId(null)}
            onSelectNode={handleSelect}
          />
        )}

        {/* Shortest-path toggle — floating top-center */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30">
          <button
            type="button"
            onClick={() => setShortestPathHighlight((v) => !v)}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-control text-[12px] font-medium border transition-all shadow-soft ${
              shortestPathHighlight
                ? 'bg-lapis/90 border-lapis/80 text-paper'
                : 'bg-peacock-dark/85 border-contour/60 text-paper/70 hover:text-paper hover:border-lapis/60'
            }`}
          >
            <GitFork strokeWidth={1.5} className="w-3.5 h-3.5" />
            Shortest path
            {shortestPathHighlight && highlightNodeIds && (
              <span className="ml-1 font-mono text-paper/80">
                {highlightNodeIds.size - 1} hops
              </span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
