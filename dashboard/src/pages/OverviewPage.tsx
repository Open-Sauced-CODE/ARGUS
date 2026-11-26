import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getInitialOverview, getInitialGraph, getOverview, getGraph } from '../api';
import { OverviewPayload, GraphPayload } from '../types';
import { useBudgetStore } from '../store/budgetStore';
import { useFindingsStore } from '../store/findingsStore';
import { useWorkspaceStore } from '../store/workspaceStore';
import { AttackGraphCanvas } from '../components/graph/AttackGraphCanvas';
import { WaitingForYou } from '../components/overview/WaitingForYou';
import { ComplianceList } from '../components/overview/ComplianceList';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';
import {
  ArrowRight,
  Activity,
  Building2,
  Sparkles,
  Cloud,
  CheckCircle2,
  Zap,
  Lock,
} from 'lucide-react';

function getGreeting(name: string): string {
  const hour = new Date().getHours();
  const timeOfDay = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  return `${timeOfDay}, ${name}`;
}

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const { k } = useBudgetStore();
  const {
    mode,
    runtimeTarget,
    workspaceRevision,
    persona,
    tenant,
    openOnboardingModal,
    openTour,
    setMode,
  } = useWorkspaceStore();

  // Initialize synchronously with store budget K
  const [overview, setOverview] = useState<OverviewPayload>(() => getInitialOverview(k));
  const [graph, setGraph] = useState<GraphPayload>(() => getInitialGraph());
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const findings = useFindingsStore((s) => s.findings);

  // Update when store K, findings, runtimeTarget, or workspaceRevision changes
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [overviewData, graphData] = await Promise.all([getOverview(k), getGraph()]);
        if (mounted) {
          setOverview(overviewData);
          setGraph(graphData);
        }
      } catch (err) {
        console.warn('Async refresh failed, using initial data:', err);
      }
    })();
    return () => { mounted = false; };
  }, [k, findings, runtimeTarget, workspaceRevision]);

  return (
    <div className="w-full space-y-5">
      {/* Dynamic Mode Notification Banner */}
      {mode === 'startup' ? (
        <section className="p-4 bg-gradient-to-r from-peacock/10 via-paper to-forest/10 border border-peacock/25 rounded-2xl shadow-xs animate-fade-in select-none">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <div className="p-2.5 bg-peacock/15 text-peacock rounded-xl border border-peacock/30 flex-shrink-0">
                <Building2 className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-headline text-base font-bold text-ink">
                    Connected Startup Tenancy: {tenant.orgName}
                  </h3>
                  <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-forest/15 text-forest rounded-full flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-forest animate-pulse" />
                    <span>{runtimeTarget === 'local' ? 'On-Device Zero Egress' : 'Active In-VPC Monitoring'}</span>
                  </span>
                  <span className="px-2 py-0.5 text-[10px] font-mono text-ink-muted bg-paper rounded border border-ink-border">
                    {overview.source_mode === 'terraform' || tenant.awsAccountId === 'local-tf'
                      ? `Terraform HCL (${tenant.region})`
                      : `AWS: ${tenant.awsAccountId} (${tenant.region})`}
                  </span>
                </div>
                <p className="text-xs text-ink-muted leading-relaxed">
                  {overview.source_mode === 'terraform' || tenant.awsAccountId === 'local-tf'
                    ? `Local Terraform & .tfvars static scanner + OPA Rego verification active on 127.0.0.1:8742 (${tenant.iamRoleArn || 'Zero network egress'}).`
                    : `Least-privilege metadata audit role active via STS delegation (${tenant.iamRoleArn}). Local inference directed to in-VPC Ollama edge agent (${tenant.ollamaEndpoint || 'http://localhost:11434'}).`}
                </p>
                <div className="flex flex-wrap items-center gap-3 pt-1 text-[11px] font-mono text-ink">
                  <span className="flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-forest" />
                    <span>{overview.graph_summary?.total_nodes ?? tenant.nodesDiscovered ?? 0} Nodes Discovered</span>
                  </span>
                  <span className="text-ink-border">•</span>
                  <span className="flex items-center gap-1">
                    <Zap className="w-3.5 h-3.5 text-peacock" />
                    <span>{overview.graph_summary?.total_edges ?? tenant.edgesDiscovered ?? 0} Multi-Hop Edges</span>
                  </span>
                  <span className="text-ink-border">•</span>
                  <span className="flex items-center gap-1">
                    <Lock className="w-3.5 h-3.5 text-peacock" />
                    <span>0 Bytes Data Egress</span>
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={openOnboardingModal}
                className="px-3 py-1.5 text-xs font-semibold bg-paper text-peacock border border-peacock/30 rounded-control hover:bg-peacock/10 transition-colors flex items-center gap-1.5 shadow-xs"
              >
                <Cloud className="w-3.5 h-3.5" />
                <span>{runtimeTarget === 'local' ? 'Scan Repo / AWS' : 'Configure AWS Role'}</span>
              </button>
              <button
                type="button"
                onClick={() => setMode('sandbox')}
                className="px-3 py-1.5 text-xs font-medium text-ink-muted hover:text-ink hover:bg-mist rounded-control border border-ink-border transition-colors"
              >
                <span>Switch to Demo Sandbox</span>
              </button>
            </div>
          </div>
        </section>
      ) : (
        <section className="p-3.5 bg-gradient-to-r from-saffron/10 via-paper to-peacock/10 border border-saffron/25 rounded-2xl shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-fade-in select-none">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-saffron/15 text-saffron-dark rounded-xl border border-saffron/30 flex-shrink-0">
              <Sparkles className="w-4 h-4 text-saffron" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-ink">
                  Campus to Cloud Hackathon • Pre-Seeded Evaluation Sandbox
                </span>
                <span className="px-1.5 py-0.5 text-[9px] font-mono font-semibold bg-saffron/20 text-ink rounded">
                  Judge Demo Mode
                </span>
              </div>
              <p className="text-[11px] text-ink-muted mt-0.5">
                Pre-loaded with 14 Indian healthtech findings, multi-hop Crown Jewel attack corridors, and 100% zero-egress proofs.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={openTour}
              className="px-3 py-1.5 text-xs font-semibold bg-peacock text-paper rounded-control hover:bg-peacock-hover transition-colors flex items-center gap-1.5 shadow-xs"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Interactive Tour</span>
            </button>
            <button
              type="button"
              onClick={() => navigate('/pipeline')}
              className="px-3 py-1.5 text-xs font-semibold bg-paper text-peacock border border-peacock/30 rounded-control hover:bg-peacock/10 transition-colors flex items-center gap-1.5 shadow-xs"
            >
              <Activity className="w-3.5 h-3.5" />
              <span>Pipeline GUI (demo.py)</span>
            </button>
          </div>
        </section>
      )}

      {/* Top Headline & Primary Action Banner */}
      <section className="space-y-2 max-w-2xl">
        <p className="text-[14px] text-ink-faint font-sans">
          {getGreeting(persona.name)}
        </p>
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          {overview.headline}
        </h1>
        <p className="text-[15px] text-ink-muted">
          {overview.subline}
        </p>
        <div className="pt-0.5 flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => navigate('/plan')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-control bg-peacock text-paper font-medium text-[13.5px] hover:bg-peacock-hover active:bg-peacock-dark transition-colors shadow-sm"
          >
            <span>{overview.action_button_label}</span>
            <ArrowRight strokeWidth={1.5} className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate('/pipeline')}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-control border border-peacock/40 bg-peacock/5 hover:bg-peacock/10 text-peacock font-medium text-[13.5px] transition-colors"
          >
            <Activity strokeWidth={1.5} className="w-4 h-4 animate-pulse" />
            <span>Live Pipeline (demo.py)</span>
          </button>
          <button
            onClick={() => navigate('/architecture')}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-control border border-ink-border bg-paper hover:bg-mist text-ink font-medium text-[13.5px] transition-colors"
          >
            <span>Hybrid Architecture</span>
            <ArrowRight strokeWidth={1.5} className="w-4 h-4 text-ink-muted" />
          </button>
          <button
            onClick={() => navigate('/results')}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-control border border-ink-border bg-paper hover:bg-mist text-ink font-medium text-[13.5px] transition-colors"
          >
            <span>Empirical Results (94.5% OOF)</span>
            <ArrowRight strokeWidth={1.5} className="w-4 h-4 text-ink-muted" />
          </button>
        </div>
      </section>

      {/* Cartographic Attack Graph Panel (Full width, ~340px tall, 20px radius) */}
      <section aria-label="Attack Path Map">
        <AttackGraphCanvas
          nodes={graph.nodes}
          edges={graph.edges}
          interdiction={overview.interdiction}
          selectedId={selectedNodeId}
          onSelect={setSelectedNodeId}
          height={340}
        />
      </section>

      {/* Lower Dual Columns: Waiting for you & Compliance with hairline divider */}
      <section className="grid grid-cols-1 lg:grid-cols-2 lg:divide-x lg:divide-ink-border">
        <div className="pr-0 lg:pr-8">
          <WaitingForYou
            findings={overview.waiting_findings}
            thresholdPct={overview.auto_apply_threshold_pct}
            certified={overview.certified}
          />
        </div>
        <div className="pl-0 lg:pl-8 mt-4 lg:mt-0">
          <ComplianceList rules={overview.compliance} />
        </div>
      </section>

      {/* System Metadata Title Block */}
      <FooterTitleBlock
        scanId={overview.scan_id}
        region={overview.region}
        scannedTime={overview.scanned_time}
        isOnDevice={overview.is_on_device}
      />
    </div>
  );
};

