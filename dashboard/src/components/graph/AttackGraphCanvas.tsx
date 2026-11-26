import React, { useRef, useEffect, useState, useCallback } from 'react';
import { iamNodes, iamEdges, iamRem, NodeKind, EdgeType } from '../../types';
import { Plus, Minus, RotateCcw } from 'lucide-react';

interface AttackGraphCanvasProps {
  nodes: iamNodes[];
  edges: iamEdges[];
  interdiction?: iamRem;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  compact?: boolean;
  className?: string;
  height?: number;
  // Map-screen filter props (optional)
  visibleKinds?: Set<NodeKind>;
  visibleEtypes?: Set<EdgeType>;
  showAttackPath?: boolean;
  showResidual?: boolean;
  /** Node IDs to visually emphasise (e.g. shortest path highlight) */
  highlightNodeIds?: Set<string>;
}

interface Point {
  x: number;
  y: number;
}

interface ScissorsHitTarget {
  source: string;
  target: string;
  x: number;
  y: number;
  radius: number;
}

// Edge-type label map for full (non-compact) mode
const ETYPE_LABELS: Record<string, string> = {
  CAN_ESCALATE: 'escalate',
  DIRECT_ADMIN: 'admin',
  CAN_ACCESS:   'access',
  RULE_TO_SG:   '→ SG',
  USES_KEY:     'uses key',
  CAN_ASSUME:   'assume',
};

export const AttackGraphCanvas: React.FC<AttackGraphCanvasProps> = ({
  nodes,
  edges,
  selectedId = null,
  onSelect,
  compact = true,
  className = '',
  height = 400,
  visibleKinds,
  visibleEtypes,
  showAttackPath = true,
  showResidual = true,
  highlightNodeIds,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Transform state: pan and zoom
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<Point>({ x: 0, y: 0 });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);

  // Animation state: default to 1.0 for instant rendering
  const [animProgress, setAnimProgress] = useState<number>(1.0);
  const animRef = useRef<number | null>(null);
  const hasAnimatedRef = useRef<boolean>(false);

  // Hit target cache for click detection
  const hitTargetsRef = useRef<Array<{ id: string; x: number; y: number; r: number }>>([]);
  const scissorsTargetsRef = useRef<ScissorsHitTarget[]>([]);

  // Check prefers-reduced-motion, headless, and orchestrate entrance
  useEffect(() => {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const isHeadless = typeof navigator !== 'undefined' && /HeadlessChrome|Lighthouse/i.test(navigator.userAgent);

    if (prefersReducedMotion || isHeadless || hasAnimatedRef.current) {
      setAnimProgress(1.0);
      hasAnimatedRef.current = true;
      return;
    }

    setAnimProgress(0);
    const startTime = performance.now();
    const duration = 800;

    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(1.0, elapsed / duration);
      setAnimProgress(progress);
      if (progress < 1.0) {
        animRef.current = requestAnimationFrame(step);
      } else {
        hasAnimatedRef.current = true;
      }
    };

    animRef.current = requestAnimationFrame(step);

    return () => {
      if (animRef.current) {
        cancelAnimationFrame(animRef.current);
      }
    };
  }, []);

  // Coordinate transformation: virtual (0-1000, 0-500) -> canvas pixels
  // Uses uniform scaling to preserve aspect ratio + centering offset
  const getCanvasCoords = useCallback(
    (vx: number, vy: number, width: number, canvasH: number): Point => {
      const virtualW = 1000;
      const virtualH = 500;
      const scale = Math.min(width / virtualW, canvasH / virtualH);
      const offsetX = (width - virtualW * scale) / 2;
      const offsetY = (canvasH - virtualH * scale) / 2;
      const px = (vx * scale + offsetX) * zoom + pan.x;
      const py = (vy * scale + offsetY) * zoom + pan.y;
      return { x: px, y: py };
    },
    [zoom, pan]
  );

  // Helper to draw kind icons inside nodes
  const drawNodeKindIcon = (ctx: CanvasRenderingContext2D, x: number, y: number, kind: string) => {
    ctx.save();
    ctx.strokeStyle = '#F9FAF8';
    ctx.fillStyle = '#F9FAF8';
    ctx.lineWidth = 1.3;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    switch (kind) {
      case 'user': {
        ctx.beginPath();
        ctx.arc(x, y - 4, 3, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y + 8, 6.5, Math.PI, 0);
        ctx.stroke();
        break;
      }
      case 'role': {
        ctx.beginPath();
        ctx.rect(x - 5, y - 6, 10, 12);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x - 3, y - 2);
        ctx.lineTo(x + 3, y - 2);
        ctx.moveTo(x - 3, y + 2);
        ctx.lineTo(x + 3, y + 2);
        ctx.stroke();
        break;
      }
      case 'sg': {
        ctx.beginPath();
        ctx.moveTo(x, y - 6);
        ctx.lineTo(x + 5.5, y - 3.5);
        ctx.lineTo(x + 5.5, y + 1.5);
        ctx.quadraticCurveTo(x + 5.5, y + 7.5, x, y + 7.5);
        ctx.quadraticCurveTo(x - 5.5, y + 7.5, x - 5.5, y + 1.5);
        ctx.lineTo(x - 5.5, y - 3.5);
        ctx.closePath();
        ctx.stroke();
        break;
      }
      case 'bucket': {
        ctx.beginPath();
        ctx.ellipse(x, y - 4, 5.5, 2, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x - 5.5, y - 4);
        ctx.lineTo(x - 4.5, y + 4.5);
        ctx.quadraticCurveTo(x, y + 6.5, x + 4.5, y + 4.5);
        ctx.lineTo(x + 5.5, y - 4);
        ctx.stroke();
        break;
      }
      case 'key': {
        ctx.beginPath();
        ctx.arc(x - 2.5, y, 3, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x + 0.5, y);
        ctx.lineTo(x + 6, y);
        ctx.moveTo(x + 4, y);
        ctx.lineTo(x + 4, y + 2.5);
        ctx.stroke();
        break;
      }
      case 'stmt': {
        ctx.beginPath();
        ctx.rect(x - 4.5, y - 5.5, 9, 11);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x - 2.5, y - 2);
        ctx.lineTo(x + 2.5, y - 2);
        ctx.moveTo(x - 2.5, y + 1.5);
        ctx.lineTo(x + 2.5, y + 1.5);
        ctx.stroke();
        break;
      }
      default: {
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
        break;
      }
    }
    ctx.restore();
  };

  // Helper to draw clean thin line-style scissors
  const drawThinLineScissors = (ctx: CanvasRenderingContext2D, x: number, y: number, edgeAngle: number) => {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(edgeAngle + Math.PI / 4);

    ctx.strokeStyle = '#F9FAF8';
    ctx.lineWidth = 1.5;
    ctx.lineCap = 'round';

    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(8, -8);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(8, 8);
    ctx.stroke();

    ctx.fillStyle = '#BE3144';
    ctx.beginPath();
    ctx.arc(0, 0, 1.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    ctx.arc(-3.5, -3.5, 3, 0, Math.PI * 2);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(-3.5, 3.5, 3, 0, Math.PI * 2);
    ctx.stroke();

    ctx.restore();
  };

  // Helper to draw clean directed arrowhead
  const drawArrowhead = (
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    angle: number,
    color: string
  ) => {
    const headLen = 9;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(
      x - headLen * Math.cos(angle - Math.PI / 6),
      y - headLen * Math.sin(angle - Math.PI / 6)
    );
    ctx.lineTo(
      x - headLen * Math.cos(angle + Math.PI / 6),
      y - headLen * Math.sin(angle + Math.PI / 6)
    );
    ctx.closePath();
    ctx.fill();
  };

  // Render routine
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    try {
      const width = canvas.clientWidth || 1000;
      const canvasHeight = canvas.clientHeight || height;
      const dpr = window.devicePixelRatio || 1;

      // Handle high-DPI scaling
      if (canvas.width !== width * dpr || canvas.height !== canvasHeight * dpr) {
        canvas.width = width * dpr;
        canvas.height = canvasHeight * dpr;
      }

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, canvasHeight);

      // 1. Draw Map Background (#0A2E33 peacock)
      ctx.fillStyle = '#0A2E33';
      ctx.fillRect(0, 0, width, canvasHeight);

      // 2. Draw Subtle Topographic Contour Lines (#1B5058)
      ctx.save();
      ctx.strokeStyle = '#1B5058';
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.28;

      ctx.beginPath();
      ctx.moveTo(-50, canvasHeight * 0.2);
      ctx.bezierCurveTo(width * 0.25, canvasHeight * 0.05, width * 0.6, canvasHeight * 0.35, width + 50, canvasHeight * 0.15);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(-50, canvasHeight * 0.5);
      ctx.bezierCurveTo(width * 0.3, canvasHeight * 0.65, width * 0.7, canvasHeight * 0.3, width + 50, canvasHeight * 0.45);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(-50, canvasHeight * 0.8);
      ctx.bezierCurveTo(width * 0.2, canvasHeight * 0.95, width * 0.8, canvasHeight * 0.7, width + 50, canvasHeight * 0.85);
      ctx.stroke();

      // Subtle coordinate grid dots
      ctx.fillStyle = '#1B5058';
      ctx.globalAlpha = 0.18;
      const dotSpacing = 38;
      for (let x = 20; x < width; x += dotSpacing) {
        for (let y = 20; y < canvasHeight; y += dotSpacing) {
          ctx.beginPath();
          ctx.arc(x, y, 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.restore();

      // Node lookup map
      const nodeMap = new Map<string, iamNodes>();
      nodes.forEach((n) => nodeMap.set(n.id, n));

      // Clear hit targets
      hitTargetsRef.current = [];
      scissorsTargetsRef.current = [];

      // 3. Draw Edges (respecting filter props)
      edges.forEach((edge) => {
        // Filter by edge type visibility
        if (visibleEtypes && !visibleEtypes.has(edge.etype)) return;

        const isAttack = edge.isAttackPath;
        const isInterdicted = edge.isInterdicted;
        const isResidual = edge.residual;

        // Filter by path visibility toggles
        if (isAttack && !showAttackPath) return;
        if (isResidual && !showResidual) return;

        const src = nodeMap.get(edge.source);
        const tgt = nodeMap.get(edge.target);
        if (!src || !tgt) return;

        // Filter by node kind visibility
        if (visibleKinds && (!visibleKinds.has(src.kind) || !visibleKinds.has(tgt.kind))) return;

        const p1 = getCanvasCoords(src.x || 100, src.y || 100, width, canvasHeight);
        const p2 = getCanvasCoords(tgt.x || 500, tgt.y || 300, width, canvasHeight);

        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist === 0) return;

        const angle = Math.atan2(dy, dx);
        const tgtRadius = tgt.isCrownJewel ? 24 : 18;
        const arrowTipX = p2.x - Math.cos(angle) * tgtRadius;
        const arrowTipY = p2.y - Math.sin(angle) * tgtRadius;

        // Dim if highlight is active and neither endpoint is highlighted
        const hasHighlight = highlightNodeIds && highlightNodeIds.size > 0;
        const edgeHighlighted = hasHighlight
          ? highlightNodeIds!.has(edge.source) && highlightNodeIds!.has(edge.target)
          : true;
        const dimAlpha = hasHighlight && !edgeHighlighted ? 0.12 : 1.0;

        ctx.save();
        ctx.globalAlpha = dimAlpha;

        if (isAttack) {
          const effectiveT = Math.min(1.0, animProgress);
          const currentEndX = p1.x + (arrowTipX - p1.x) * effectiveT;
          const currentEndY = p1.y + (arrowTipY - p1.y) * effectiveT;

          if (isInterdicted) {
            ctx.strokeStyle = '#BE3144';
            ctx.lineWidth = 2.4;
            ctx.setLineDash([6, 5]);
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(currentEndX, currentEndY);
            ctx.stroke();

            if (effectiveT > 0.5) {
              const midX = (p1.x + arrowTipX) / 2;
              const midY = (p1.y + arrowTipY) / 2;

              drawThinLineScissors(ctx, midX, midY, angle);

              scissorsTargetsRef.current.push({
                source: edge.source,
                target: edge.target,
                x: midX,
                y: midY,
                radius: 14,
              });
            }
          } else {
            ctx.strokeStyle = '#BE3144';
            ctx.lineWidth = 2.6;
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(currentEndX, currentEndY);
            ctx.stroke();

            if (effectiveT >= 0.95) {
              drawArrowhead(ctx, arrowTipX, arrowTipY, angle, '#BE3144');
            }
          }
        } else if (isResidual) {
          ctx.strokeStyle = '#52B2A0';
          ctx.globalAlpha = dimAlpha * 0.85;
          ctx.lineWidth = 1.8;
          ctx.setLineDash([5, 4]);
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(arrowTipX, arrowTipY);
          ctx.stroke();

          drawArrowhead(ctx, arrowTipX, arrowTipY, angle, '#52B2A0');
        } else {
          ctx.strokeStyle = '#1B5058';
          ctx.globalAlpha = dimAlpha * 0.45;
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(arrowTipX, arrowTipY);
          ctx.stroke();

          drawArrowhead(ctx, arrowTipX, arrowTipY, angle, '#1B5058');
        }

        // Edge-type label in full (non-compact) mode
        if (!compact && dist > 60) {
          const labelX = (p1.x + arrowTipX) / 2 + Math.sin(angle) * -14;
          const labelY = (p1.y + arrowTipY) / 2 + Math.cos(angle) * 14;
          const etypeLabel = ETYPE_LABELS[edge.etype] ?? edge.etype;
          ctx.globalAlpha = dimAlpha * 0.65;
          ctx.fillStyle = isAttack ? '#BE3144' : isResidual ? '#52B2A0' : '#F9FAF8';
          ctx.font = '10px "Hanken Grotesk", sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(etypeLabel, labelX, labelY);
        }

        ctx.restore();
      });

      // 4. Draw Nodes (respecting filter props)
      nodes.forEach((node) => {
        // Filter by kind visibility
        if (visibleKinds && !visibleKinds.has(node.kind)) return;

        const pos = getCanvasCoords(node.x || 100, node.y || 100, width, canvasHeight);
        const isSelected = selectedId === node.id || focusedNodeId === node.id;
        const isHovered = hoveredNodeId === node.id;
        const isHighlighted = !highlightNodeIds || highlightNodeIds.size === 0 || highlightNodeIds.has(node.id);
        const nodeRadius = node.isCrownJewel ? 19 : 16;

        hitTargetsRef.current.push({
          id: node.id,
          x: pos.x,
          y: pos.y,
          r: nodeRadius + 8,
        });

        ctx.save();
        // Dim nodes not in highlight set
        ctx.globalAlpha = isHighlighted ? 1.0 : 0.2;

        if (isSelected || isHovered) {
          ctx.strokeStyle = isSelected ? '#F9FAF8' : '#2E9C82';
          ctx.lineWidth = 2.5;
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, nodeRadius + 6, 0, Math.PI * 2);
          ctx.stroke();
        }

        if (node.isCrownJewel) {
          ctx.shadowColor = 'rgba(181, 138, 60, 0.45)';
          ctx.shadowBlur = 18;

          const s = 20;
          ctx.fillStyle = '#B58A3C';
          ctx.beginPath();
          ctx.moveTo(pos.x, pos.y - s);
          ctx.lineTo(pos.x + s, pos.y);
          ctx.lineTo(pos.x, pos.y + s);
          ctx.lineTo(pos.x - s, pos.y);
          ctx.closePath();
          ctx.fill();

          ctx.strokeStyle = '#F9FAF8';
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.moveTo(pos.x, pos.y - s * 0.55);
          ctx.lineTo(pos.x + s * 0.55, pos.y);
          ctx.lineTo(pos.x, pos.y + s * 0.55);
          ctx.lineTo(pos.x - s * 0.55, pos.y);
          ctx.closePath();
          ctx.stroke();

          drawNodeKindIcon(ctx, pos.x, pos.y, 'bucket');

          ctx.shadowBlur = 0;
          ctx.fillStyle = '#B58A3C';
          ctx.font = '600 12px "Hanken Grotesk", sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText('CROWN JEWEL', pos.x, pos.y + s + 22);
        } else if (node.isEntry) {
          ctx.fillStyle = '#0A2E33';
          ctx.strokeStyle = '#BE3144';
          ctx.lineWidth = 2.4;
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, nodeRadius, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();

          drawNodeKindIcon(ctx, pos.x, pos.y, node.kind);

          ctx.fillStyle = '#BE3144';
          ctx.font = '600 12px "Hanken Grotesk", sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText('ENTRY POINT', pos.x, pos.y + nodeRadius + 22);
        } else {
          let fillCol = '#13474F';
          let strokeCol = '#1B5058';

          if (node.kind === 'role') {
            fillCol = '#0E3B42';
            strokeCol = '#4C6EA8';
          } else if (node.kind === 'sg') {
            fillCol = '#11353B';
            strokeCol = '#E2992A';
          } else if (node.kind === 'stmt') {
            fillCol = '#1A2930';
            strokeCol = '#BE3144';
          } else if (node.kind === 'key') {
            fillCol = '#13474F';
            strokeCol = '#2E9C82';
          }

          ctx.fillStyle = fillCol;
          ctx.strokeStyle = strokeCol;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, nodeRadius, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();

          drawNodeKindIcon(ctx, pos.x, pos.y, node.kind);
        }

        ctx.fillStyle = '#F9FAF8';
        ctx.font = '500 13px "Hanken Grotesk", sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        const labelY = node.isCrownJewel ? pos.y + 24 : pos.y + nodeRadius + 4;
        ctx.fillText(node.label, pos.x, labelY);

        ctx.restore();
      });

      ctx.restore();
    } catch (err: any) {
      console.error('Canvas render error:', err);
      ctx.fillStyle = '#BE3144';
      ctx.font = '14px sans-serif';
      ctx.fillText('Render error: ' + (err?.message || String(err)), 20, 40);
    }
  }, [
    nodes,
    edges,
    animProgress,
    getCanvasCoords,
    selectedId,
    hoveredNodeId,
    focusedNodeId,
    height,
    compact,
    visibleKinds,
    visibleEtypes,
    showAttackPath,
    showResidual,
    highlightNodeIds,
  ]);

  // Redraw when properties, animation, or pan/zoom update
  useEffect(() => {
    render();
  }, [render]);

  // Handle Resize Crispness with ResizeObserver
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => {
      render();
    });
    observer.observe(container);
    window.addEventListener('resize', render);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', render);
    };
  }, [render]);

  // Mouse interaction: Drag / Pan & Hit Testing
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    if (isDragging) {
      setPan({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
      return;
    }

    let foundNode: string | null = null;
    for (const target of hitTargetsRef.current) {
      const dist = Math.hypot(mouseX - target.x, mouseY - target.y);
      if (dist <= target.r) {
        foundNode = target.id;
        break;
      }
    }
    setHoveredNodeId(foundNode);
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDragging) return;
    setIsDragging(false);

    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    for (const sTarget of scissorsTargetsRef.current) {
      const dist = Math.hypot(clickX - sTarget.x, clickY - sTarget.y);
      if (dist <= sTarget.radius) {
        if (onSelect) onSelect(sTarget.source);
        return;
      }
    }

    for (const target of hitTargetsRef.current) {
      const dist = Math.hypot(clickX - target.x, clickY - target.y);
      if (dist <= target.r) {
        if (onSelect) onSelect(target.id === selectedId ? null : target.id);
        return;
      }
    }
  };

  // Zoom controls
  const handleZoomIn = () => setZoom((z) => Math.min(2.0, z + 0.15));
  const handleZoomOut = () => setZoom((z) => Math.max(0.65, z - 0.15));
  const handleReset = () => {
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
    if (onSelect) onSelect(null);
  };

  return (
    <div
      ref={containerRef}
      className={`relative w-full overflow-hidden bg-peacock select-none ${compact ? 'rounded-panel shadow-soft' : ''} ${className}`}
      style={height ? { height: `${height}px` } : { height: '100%' }}
    >
      {/* 2D Canvas */}
      <canvas
        ref={canvasRef}
        width={1120}
        height={height || 600}
        className="w-full h-full block cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      />

      {/* Accessible visually hidden layer of focusable buttons mirroring canvas */}
      <div className="sr-only" aria-label="Interactive Cloud Attack Graph Nodes">
        {nodes.map((node) => (
          <button
            key={node.id}
            type="button"
            aria-label={`${node.kind}, risk score ${node.risk}, label: ${node.label}${
              node.isCrownJewel ? ', Crown jewel target' : ''
            }${node.isEntry ? ', Attacker entry point' : ''}`}
            onFocus={() => {
              setFocusedNodeId(node.id);
              if (onSelect) onSelect(node.id);
            }}
            onBlur={() => setFocusedNodeId(null)}
            onClick={() => onSelect && onSelect(node.id)}
          >
            {node.label}
          </button>
        ))}
      </div>

      {/* Zoom Controls Top-Right (adjusts when detail panel is open) */}
      <div
        className={`absolute top-4 ${
          compact ? 'right-4' : selectedId ? 'right-80' : 'right-4'
        } transition-all duration-200 flex items-center gap-1.5 bg-peacock-dark/85 backdrop-blur-sm border border-contour/50 rounded-control p-1 text-paper shadow-sm z-10`}
      >
        <button
          type="button"
          onClick={handleZoomIn}
          aria-label="Zoom in"
          className="p-1.5 hover:bg-peacock-light rounded text-paper/80 hover:text-paper transition-colors"
        >
          <Plus strokeWidth={1.5} className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={handleZoomOut}
          aria-label="Zoom out"
          className="p-1.5 hover:bg-peacock-light rounded text-paper/80 hover:text-paper transition-colors"
        >
          <Minus strokeWidth={1.5} className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={handleReset}
          aria-label="Reset zoom and center"
          className="p-1.5 hover:bg-peacock-light rounded text-paper/80 hover:text-paper transition-colors"
        >
          <RotateCcw strokeWidth={1.5} className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Cartographic Legend — bottom-left in compact, bottom-center in full */}
      <div className={`absolute ${compact ? 'bottom-4 left-4' : 'bottom-4 left-1/2 -translate-x-1/2'} bg-peacock-dark/85 backdrop-blur-sm border border-contour/50 rounded-control py-2 px-3.5 text-[12px] text-paper shadow-sm`}>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-3.5 h-0.5 bg-garnet inline-block" />
            <span className="text-paper/90">Attack path</span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="w-3.5 h-0.5 bg-[#52B2A0] inline-block" />
            <span className="text-paper/90">Residual path</span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[12px] text-paper/90 font-bold">✂</span>
            <span className="text-paper/90">Interdicted</span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 bg-brass rotate-45 inline-block shadow-brass" />
            <span className="text-paper/90 font-medium">Crown jewel</span>
          </div>
        </div>
      </div>
    </div>
  );
};
