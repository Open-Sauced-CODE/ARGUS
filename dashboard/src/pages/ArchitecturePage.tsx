import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Cpu,
  CheckCircle2,
  FileCode2,
  Server,
  Terminal,
  Play,
  RotateCcw,
  ShieldAlert,
  Clock,
  Zap,
  Globe,
  Monitor,
  ArrowRight,
  BarChart3,
  BookOpen,
  Download,
} from 'lucide-react';
import { getArchitecture, runLivePipeline, resetPipeline, getFindings } from '../api';
import { useWorkspaceStore } from '../store/workspaceStore';
import { ArchitecturePayload, PipelineExecutionResult } from '../types';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';

export const ArchitecturePage: React.FC = () => {
  const { runtimeTarget, workspaceRevision, tenant } = useWorkspaceStore();
  const [arch, setArch] = useState<ArchitecturePayload | null>(null);
  const [selectedScenario, setSelectedScenario] = useState<string>('public');
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [pipelineResult, setPipelineResult] = useState<PipelineExecutionResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const data = await getArchitecture();
        if (mounted) setArch(data);
      } catch (err) {
        console.warn('Failed to load architecture spec:', err);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [runtimeTarget, workspaceRevision]);

  const handleRunScenario = async () => {
    setIsRunning(true);
    setErrorMsg(null);
    setPipelineResult(null);
    try {
      const res = await runLivePipeline(selectedScenario);
      setPipelineResult(res);
      // Immediately sync findings store with newly synthesized remediation
      await getFindings().catch(() => {});
    } catch (err: any) {
      setErrorMsg(err?.message || 'Pipeline execution failed');
    } finally {
      setIsRunning(false);
    }
  };

  const handleReset = async () => {
    try {
      await resetPipeline();
      await getFindings().catch(() => {});
      setPipelineResult(null);
      setErrorMsg(null);
    } catch (err: any) {
      console.warn('Reset failed:', err);
    }
  };

  const scenarios = [
    {
      key: 'public',
      label: 'S3 Public Access Block Disabled [DPDP Rule 6]',
      severity: 'CRITICAL',
      resource: 'indian-citizen-medical-records-store',
    },
    {
      key: 'encryption',
      label: 'S3 Bucket Missing KMS Encryption [CIS 2.1.1]',
      severity: 'CRITICAL',
      resource: 'production-finance-ledger-2026',
    },
    {
      key: 'admin',
      label: 'IAM Full Admin Wildcard Policy [CIS 1.16]',
      severity: 'HIGH',
      resource: 'developer-temp-admin-policy',
    },
    {
      key: 'logging',
      label: 'S3 Access Logging Inactive [DPDP Rule 7]',
      severity: 'MEDIUM',
      resource: 'customer-pii-audit-storage',
    },
  ];

  return (
    <div className="w-full space-y-8 pb-12">
      {/* 1. Page Header */}
      <section className="space-y-2 max-w-3xl">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold text-peacock bg-peacock/10 rounded-full">
            <Cpu className="w-3.5 h-3.5" />
            <span>Architecture & Deployment Guide</span>
          </span>
          <span className="text-xs text-ink-muted">AWS ap-south-1 (Mumbai)</span>
        </div>
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          Autonomous Cloud Remediation for Non-DPDP Compliant Startups
        </h1>
        <p className="text-[15px] text-ink-muted leading-relaxed">
          How Indian startups & campuses combine the AWS Free Tier Showcase Portal with a 100% on-device Local Execution Engine
          to achieve India DPDP Act 2023 compliance with zero customer data egress.
        </p>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Link
            to="/results"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control bg-peacock text-paper text-xs font-semibold hover:bg-peacock-hover transition-colors"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span>View Empirical Results (94.48% OOF)</span>
          </Link>
          <Link
            to="/docs"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control bg-paper border border-ink-border text-ink text-xs font-semibold hover:bg-mist transition-colors"
          >
            <BookOpen className="w-3.5 h-3.5 text-peacock" />
            <span>DPDP & IAM Docs</span>
          </Link>
          <Link
            to="/downloads"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control bg-paper border border-ink-border text-ink text-xs font-semibold hover:bg-mist transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-forest" />
            <span>Desktop Versions & .exe</span>
          </Link>
        </div>
      </section>

      {/* 1b. Hybrid Architecture Deployment Split (EC2 Showcase <-> Browser Bridge <-> Local Engine) */}
      <section className="bg-paper border border-ink-border rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-ink-border/60 pb-3">
          <div>
            <h2 className="font-headline text-xl text-ink font-semibold">
              Hybrid Deployment Split (Compute Physics + DPDP Zero Egress)
            </h2>
            <p className="text-xs text-ink-muted mt-0.5">
              Active Mode: <strong className="text-peacock">{runtimeTarget === 'local' ? 'Local Desktop Engine (127.0.0.1:8742)' : 'AWS Free Tier Showcase (13.201.224.53)'}</strong>
            </p>
          </div>
          <span className="px-2.5 py-1 text-[11px] font-mono bg-forest/10 text-forest border border-forest/25 rounded-full font-semibold">
            0 Bytes Customer Secrets on EC2
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-11 gap-3 items-stretch">
          <div className="lg:col-span-5 p-4 bg-mist/40 border border-ink-border rounded-xl space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-semibold text-sm text-ink">
                <Globe className="w-4 h-4 text-peacock" />
                <span>1. Public Web Portal (AWS Free Tier)</span>
              </div>
              <span className="text-[10px] font-mono bg-paper px-2 py-0.5 rounded border border-ink-border">
                13.201.224.53
              </span>
            </div>
            <p className="text-[11.5px] text-ink-muted">
              EC2 <code className="font-mono">t3.micro</code> (<code className="font-mono">ap-south-1</code> Mumbai, 1 GB RAM) hosts React SPA, SwasthyaPay Judge Sandbox, animated 6-stage pipeline, Empirical Benchmarks, Documentation, and Desktop Releases.
            </p>
            <ul className="text-[11px] text-ink space-y-1">
              <li>• Strictly zero customer AWS keys or PII stored</li>
              <li>• Blocks <code className="font-mono">/api/scan/*</code> with 403 Zero-Egress guard</li>
            </ul>
          </div>

          <div className="lg:col-span-1 flex items-center justify-center py-1">
            <div className="flex lg:flex-col items-center gap-1 text-[10px] font-mono text-peacock font-semibold">
              <ArrowRight className="w-4 h-4 hidden lg:block" />
              <span>Bridge</span>
              <span className="text-ink-faint">Loopback</span>
            </div>
          </div>

          <div className="lg:col-span-5 p-4 bg-forest/5 border border-forest/30 rounded-xl space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-semibold text-sm text-ink">
                <Monitor className="w-4 h-4 text-forest" />
                <span>2. Local Customer / VPC Engine</span>
              </div>
              <span className="text-[10px] font-mono bg-paper text-forest px-2 py-0.5 rounded border border-forest/30">
                127.0.0.1:8742
              </span>
            </div>
            <p className="text-[11.5px] text-ink-muted">
              Runs inside startup workstation or private VPC: Terraform + AWS boto3 (<code className="font-mono">iam_guard</code> enforced), In-Memory Cartography + MILP, Fernet Airlock Vault, Ollama <code className="font-mono">argus-m1-sft</code>, bundled <code className="font-mono">opa.exe</code>, <code className="font-mono">.patch</code> exporter.
            </p>
            <ul className="text-[11px] text-ink space-y-1">
              <li>• Persistent SQLite (<code className="font-mono">argus_state.db</code> + <code className="font-mono">vault.db</code>)</li>
              <li>• Autonomy OFF until M2 <code className="font-mono">tau_star.json</code> certified</li>
            </ul>
          </div>
        </div>
      </section>

      {/* 2. Startup Case Study: SwasthyaPay Technologies */}
      <section className="bg-paper border border-ink-border rounded-xl p-6 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-ink-border/60 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-ink text-base">Case Study: SwasthyaPay Technologies</span>
              <span className="px-2 py-0.5 text-[11px] font-mono bg-mist text-ink-muted rounded">
                Series A FinTech / HealthTech
              </span>
            </div>
            <p className="text-xs text-ink-muted mt-0.5">
              Handling 4.2M Indian citizen health cards, Aadhaar KYC documents, and UPI transaction ledgers.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold bg-terracotta/10 text-terracotta rounded">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>DPDP Penalty Exposure: ₹250 Crores</span>
            </span>
          </div>
        </div>

        {/* Before vs After Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Before */}
          <div className="p-4 bg-terracotta/5 border border-terracotta/20 rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-terracotta uppercase tracking-wider">Before ARGUS</span>
              <span className="text-xs font-mono text-terracotta bg-terracotta/10 px-2 py-0.5 rounded">Critical Risk</span>
            </div>
            <ul className="text-xs space-y-2 text-ink">
              <li className="flex items-start gap-2">
                <span className="text-terracotta font-bold">•</span>
                <span><strong>12 Active DPDP / CIS Violations:</strong> Public S3 buckets, unencrypted databases, wildcard IAM policies.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-terracotta font-bold">•</span>
                <span><strong>90.6% Attack Path Likelihood:</strong> Leaked developer key can escalate to full cloud admin and steal customer KYC.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-terracotta font-bold">•</span>
                <span><strong>Statutory Exposure:</strong> ₹250 Cr statutory penalties under DPDP Act 2023 Section 33.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-terracotta font-bold">•</span>
                <span><strong>The AI Cloud Dilemma:</strong> Cannot send proprietary configs or customer data to commercial cloud LLMs (OpenAI/Anthropic).</span>
              </li>
            </ul>
          </div>

          {/* After */}
          <div className="p-4 bg-forest/5 border border-forest/20 rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-forest uppercase tracking-wider">After ARGUS In-VPC</span>
              <span className="text-xs font-mono text-forest bg-forest/10 px-2 py-0.5 rounded">100% Certified</span>
            </div>
            <ul className="text-xs space-y-2 text-ink">
              <li className="flex items-start gap-2">
                <span className="text-forest font-bold">•</span>
                <span><strong>0 Critical Violations:</strong> Autonomous generation of Terraform HCL security configurations.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-forest font-bold">•</span>
                <span><strong>58.6% Residual Exposure (K=3):</strong> Cutting just 3 bottleneck edges severs attacker reach to Crown Jewels.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-forest font-bold">•</span>
                <span><strong>Zero-Data-Egress Proof:</strong> 0.00 bytes transmitted outside AWS ap-south-1. HMAC-SHA256 cryptographic receipt.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-forest font-bold">•</span>
                <span><strong>Sub-3.5s Autonomous Synthesis:</strong> Local Ollama 4B model (argus-m1-sft) + OPA Rego verification gate.</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* 3. The 6-Stage End-to-End Pipeline */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-headline text-xl text-ink font-semibold">
            End-to-End Pipeline Architecture
          </h2>
          <span className="text-xs text-ink-muted">6 Autonomous Stages</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {arch?.pipeline_layers?.map((layer) => (
            <div
              key={layer.layer}
              className="p-4 bg-paper border border-ink-border rounded-xl shadow-xs space-y-2 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="w-6 h-6 rounded-full bg-peacock/10 text-peacock font-mono text-xs font-bold flex items-center justify-center">
                    {layer.layer}
                  </span>
                  <span className="text-[11px] text-ink-muted font-mono uppercase tracking-wider">
                    Stage {layer.layer}
                  </span>
                </div>
                <h3 className="text-sm font-semibold text-ink">{layer.name}</h3>
                <p className="text-xs text-ink-muted mt-1 leading-relaxed">{layer.purpose}</p>
              </div>

              <div className="pt-2 border-t border-ink-border/50">
                <div className="flex flex-wrap gap-1">
                  {layer.components.map((comp, i) => (
                    <span
                      key={i}
                      className="inline-block px-1.5 py-0.5 text-[10px] font-mono bg-mist text-ink-muted rounded"
                    >
                      {comp}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 4. Interactive Live Demonstration Sandbox */}
      <section className="bg-paper border border-ink-border rounded-xl p-6 shadow-sm space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-ink-border/60 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <Terminal className="w-5 h-5 text-peacock" />
              <h2 className="font-headline text-xl text-ink font-semibold">
                Live Remediation Demonstration Sandbox
              </h2>
            </div>
            <p className="text-xs text-ink-muted mt-1">
              Test ARGUS live on your machine: invokes local Ollama (argus-m1-sft) + HMAC Airlock + OPA Rego Verification Gate.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="px-3 py-1.5 text-xs text-ink-muted hover:text-ink border border-ink-border rounded-control hover:bg-mist transition-colors flex items-center gap-1.5"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset State</span>
            </button>
            <button
              onClick={handleRunScenario}
              disabled={isRunning}
              className="px-4 py-1.5 text-xs font-medium bg-peacock text-paper rounded-control hover:bg-peacock-hover active:bg-peacock-dark transition-colors shadow-sm flex items-center gap-1.5 disabled:opacity-50"
            >
              {isRunning ? (
                <>
                  <Zap className="w-3.5 h-3.5 animate-spin" />
                  <span>Synthesizing (Ollama)...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Execute Live Pipeline</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Scenario Selection Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          {scenarios.map((sc) => {
            const isSelected = selectedScenario === sc.key;
            return (
              <button
                key={sc.key}
                type="button"
                onClick={() => setSelectedScenario(sc.key)}
                className={`p-3 text-left rounded-lg border transition-all ${
                  isSelected
                    ? 'border-peacock bg-peacock/5 ring-1 ring-peacock'
                    : 'border-ink-border/80 bg-mist/30 hover:bg-mist/60'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span
                    className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                      sc.severity === 'CRITICAL'
                        ? 'bg-terracotta/10 text-terracotta font-bold'
                        : 'bg-saffron/10 text-saffron font-bold'
                    }`}
                  >
                    {sc.severity}
                  </span>
                  {isSelected && <span className="text-xs text-peacock font-semibold">Active</span>}
                </div>
                <p className="text-xs font-semibold text-ink leading-tight line-clamp-2">{sc.label}</p>
                <p className="text-[11px] font-mono text-ink-muted truncate mt-1">{sc.resource}</p>
              </button>
            );
          })}
        </div>

        {/* Live Execution Output Area */}
        {errorMsg && (
          <div className="p-3 bg-terracotta/10 border border-terracotta/30 text-terracotta text-xs rounded-lg">
            Error: {errorMsg}
          </div>
        )}

        {isRunning && (
          <div className="p-8 text-center space-y-3 bg-mist/30 border border-dashed border-ink-border rounded-xl">
            <Zap className="w-8 h-8 text-peacock animate-bounce mx-auto" />
            <p className="text-sm font-semibold text-ink">Running Real ARGUS Pipeline in Real-Time...</p>
            <p className="text-xs text-ink-muted font-mono">
              [1] Ingestion &rarr; [2] HMAC Airlock &rarr; [3] PageRank &rarr; [4] Local Ollama Model (argus-m1-sft) &rarr; [5] Rego Policy Gate
            </p>
          </div>
        )}

        {pipelineResult && (
          <div className="space-y-4 animate-fade-in pt-2">
            {/* Telemetry Summary Bar */}
            <div className="p-3 bg-forest/10 border border-forest/30 rounded-lg flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-forest" />
                <span className="text-xs font-semibold text-ink">
                  Pipeline Execution Complete for {pipelineResult.title}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="text-ink-muted flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  <span>Total Latency: <strong>{pipelineResult.total_latency_ms} ms</strong></span>
                </span>
                <span className="text-forest bg-forest/20 px-2 py-0.5 rounded font-bold">
                  0 Bytes Leaked
                </span>
              </div>
            </div>

            {/* Stages Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 text-xs">
              {pipelineResult.stages.map((st) => (
                <div key={st.stage} className="p-2.5 bg-mist/50 border border-ink-border/70 rounded-lg space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-ink">Stage {st.stage}: {st.name}</span>
                    <span className="font-mono text-[10px] text-ink-muted">{st.latency_ms} ms</span>
                  </div>
                  <p className="text-ink-muted text-[11px] leading-tight">{st.details}</p>
                </div>
              ))}
            </div>

            {/* Code Output Split View */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Patch-IR (JSON) */}
              <div className="p-4 bg-paper border border-ink-border rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-ink flex items-center gap-1.5">
                    <FileCode2 className="w-3.5 h-3.5 text-peacock" />
                    <span>Synthesized Patch-IR (Ollama argus-m1-sft)</span>
                  </span>
                  <span className="text-[10px] font-mono text-peacock bg-peacock/10 px-2 py-0.5 rounded">
                    GBNF Grammar Validated
                  </span>
                </div>
                <pre className="p-3 bg-mist/70 border border-ink-border/60 rounded text-[11px] font-mono text-ink overflow-x-auto max-h-48 leading-relaxed">
                  {JSON.stringify(pipelineResult.patch_ir, null, 2)}
                </pre>
              </div>

              {/* Remediated Terraform Diff */}
              <div className="p-4 bg-paper border border-ink-border rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-ink flex items-center gap-1.5">
                    <FileCode2 className="w-3.5 h-3.5 text-forest" />
                    <span>Autonomous Terraform HCL Diff</span>
                  </span>
                  <span className="text-[10px] font-mono text-forest bg-forest/10 px-2 py-0.5 rounded">
                    Atomic Git Commit Ready
                  </span>
                </div>
                <pre className="p-3 bg-mist/70 border border-ink-border/60 rounded text-[11px] font-mono text-ink overflow-x-auto max-h-48 leading-relaxed">
                  {pipelineResult.diff.after}
                </pre>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* 5. Small Startup Deployment Topology */}
      <section className="bg-paper border border-ink-border rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-ink-border/60 pb-3">
          <div className="flex items-center gap-2">
            <Server className="w-5 h-5 text-peacock" />
            <h2 className="font-headline text-xl text-ink font-semibold">
              Deployment Topologies for Seed / Growth Startups
            </h2>
          </div>
          <span className="text-xs text-ink-muted">AWS ap-south-1 Mumbai</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {arch?.deployment_options?.map((dep, idx) => (
            <div key={idx} className="p-4 bg-mist/40 border border-ink-border rounded-lg space-y-2">
              <span className="text-xs font-mono font-bold text-peacock bg-peacock/10 px-2 py-0.5 rounded inline-block">
                {dep.cost}
              </span>
              <h3 className="text-sm font-semibold text-ink">{dep.type}</h3>
              <p className="text-xs text-ink-muted leading-relaxed">{dep.description}</p>
            </div>
          ))}
        </div>

        <div className="p-4 bg-mist/60 border border-ink-border rounded-lg text-xs text-ink space-y-2">
          <p className="font-semibold text-ink">How Engineers Access & Use ARGUS in Production:</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            <div className="p-2.5 bg-paper rounded border border-ink-border/60">
              <span className="font-mono font-bold text-peacock block mb-1">1. Developer CLI</span>
              <p className="text-ink-muted">
                Run <code>python demo.py --scenario public</code> directly from terminal or local workstation to remediate IaC misconfigurations before push.
              </p>
            </div>
            <div className="p-2.5 bg-paper rounded border border-ink-border/60">
              <span className="font-mono font-bold text-peacock block mb-1">2. CI/CD GitHub Action</span>
              <p className="text-ink-muted">
                Automatically scans every Pull Request. Certified fixes generate an automated branch and commit diff with zero human editing.
              </p>
            </div>
            <div className="p-2.5 bg-paper rounded border border-ink-border/60">
              <span className="font-mono font-bold text-peacock block mb-1">3. Executive Web Dashboard</span>
              <p className="text-ink-muted">
                View DPDP Act readiness, attack graph blast radius, Pareto interdiction curves, and approve flagged high-impact infrastructure changes.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer System Block */}
      <FooterTitleBlock
        scanId={runtimeTarget === 'local' ? 'local-architecture' : 'scan-swasthya-mumbai-042'}
        region={tenant.region || 'ap-south-1 (Mumbai, India)'}
        scannedTime={new Date().toISOString()}
        isOnDevice={runtimeTarget === 'local'}
      />
    </div>
  );
};
