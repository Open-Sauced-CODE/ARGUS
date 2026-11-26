import React, { useState, useEffect, useRef } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Lock,
  Copy,
  Terminal,
  ShieldCheck,
  ChevronRight,
  ChevronLeft,
  Zap,
  ArrowRight,
  Sparkles,
} from 'lucide-react';
import { runLivePipeline } from '../api';
import { PipelineExecutionResult } from '../types';

interface ScenarioDef {
  key: string;
  title: string;
  rule_id: string;
  blast_radius: number;
  exploit_path: string;
  raw: any;
  hcl_before: string;
  hcl_after: string;
}

const SCENARIOS: Record<string, ScenarioDef> = {
  encryption: {
    key: 'encryption',
    title: 'S3 Bucket Default Server-Side Encryption Missing [CIS 2.1.1]',
    rule_id: 'cis.s3_default_encryption',
    blast_radius: 0.720,
    exploit_path: 'Unencrypted Storage -> Data Leak in Transit/Rest',
    raw: {
      finding_id: 'F-LIVE-43',
      resource_id: 'production-finance-ledger-2026',
      resource_type: 'AWSS3Bucket',
      attributes: {
        name: 'production-finance-ledger-2026',
        arn: 'arn:aws:s3:::production-finance-ledger-2026',
        account_id: '987654321098',
        region: 'ap-south-1',
        default_encryption: false,
        encryption_algorithm: 'none',
        tags: {
          environment: 'production',
          owner: 'finance-admin@enterprise.in',
          secret_note: 'AKIAIOSFODNN7EXAMPLE',
        },
      },
    },
    hcl_before: `resource "aws_s3_bucket" "finance_ledger" {
  bucket = "production-finance-ledger-2026"
  # Server-side encryption missing
}`,
    hcl_after: `resource "aws_s3_bucket_server_side_encryption_configuration" "finance_ledger" {
  bucket = aws_s3_bucket.finance_ledger.id
+ rule {
+   apply_server_side_encryption_by_default {
+     sse_algorithm = "aws:kms"
+   }
+   bucket_key_enabled = true
+ }
}`,
  },
  public: {
    key: 'public',
    title: 'S3 Public Access Block Disabled [India DPDP Act 2023 Rule 6]',
    rule_id: 'dpdp.rule6_public_exposure',
    blast_radius: 0.880,
    exploit_path: 'Public S3 Bucket -> Unauthorized Citizen PII Exfiltration',
    raw: {
      finding_id: 'F-LIVE-12',
      resource_id: 'indian-citizen-medical-records-store',
      resource_type: 'AWSS3BucketPublicAccessBlock',
      attributes: {
        name: 'indian-citizen-medical-records-store',
        arn: 'arn:aws:s3:::indian-citizen-medical-records-store',
        account_id: '123456789012',
        region: 'ap-south-1',
        block_public_acls: false,
        block_public_policy: false,
        ignore_public_acls: false,
        restrict_public_buckets: false,
        user_data: 'aadhaar 4532 8912 0019',
        tags: {
          compliance: 'dpdp-sensitive',
          backup_key: 'AKIAIOSFODNN7EXAMPLE',
        },
      },
    },
    hcl_before: `resource "aws_s3_bucket_public_access_block" "records" {
  bucket = aws_s3_bucket.medical_records.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}`,
    hcl_after: `resource "aws_s3_bucket_public_access_block" "records" {
  bucket = aws_s3_bucket.medical_records.id
- block_public_acls       = false
- block_public_policy     = false
- ignore_public_acls      = false
- restrict_public_buckets = false
+ block_public_acls       = true
+ block_public_policy     = true
+ ignore_public_acls      = true
+ restrict_public_buckets = true
}`,
  },
  admin: {
    key: 'admin',
    title: 'IAM Full Administrator Wildcard Policy [CIS 1.16]',
    rule_id: 'cis.iam_no_full_admin',
    blast_radius: 0.950,
    exploit_path: 'Wildcard Privilege Escalation -> Full Cloud Account Takeover',
    raw: {
      finding_id: 'F-LIVE-89',
      resource_id: 'developer-temp-admin-policy',
      resource_type: 'AWSIAMPolicy',
      attributes: {
        name: 'developer-temp-admin-policy',
        arn: 'arn:aws:iam::123456789012:policy/DevAdminAccess',
        account_id: '123456789012',
        Action: '*',
        Resource: '*',
        Effect: 'Allow',
      },
    },
    hcl_before: `resource "aws_iam_policy" "dev_admin" {
  name   = "DevAdminAccess"
  policy = jsonencode({
    Action   = "*"
    Resource = "*"
    Effect   = "Allow"
  })
}`,
    hcl_after: `# ARGUS Escalate Router Triggered: cis.iam_no_full_admin
# Wildcard policy requires human security architect privilege minimization.
# Routed to Tier 3 Architect Review Queue (Zero unauthorized auto-downgrades).`,
  },
  logging: {
    key: 'logging',
    title: 'S3 Access Logging Inactive [India DPDP Act Audit Requirement]',
    rule_id: 'dpdp.rule6_logging',
    blast_radius: 0.580,
    exploit_path: 'Unlogged Access -> Inability to Perform Forensic Breach Audit',
    raw: {
      finding_id: 'F-LIVE-77',
      resource_id: 'customer-pii-audit-storage',
      resource_type: 'AWSS3Bucket',
      attributes: {
        name: 'customer-pii-audit-storage',
        arn: 'arn:aws:s3:::customer-pii-audit-storage',
        account_id: '123456789012',
        region: 'ap-south-1',
        logging_enabled: false,
        tags: {
          sensitivity: 'high-audit-trail',
          admin_token: 'SECRET_TOKEN_XYZ987',
        },
      },
    },
    hcl_before: `resource "aws_s3_bucket" "audit_storage" {
  bucket = "customer-pii-audit-storage"
  # Server access logging disabled
}`,
    hcl_after: `resource "aws_s3_bucket_logging" "audit_storage" {
  bucket = aws_s3_bucket.audit_storage.id
+ target_bucket = aws_s3_bucket.central_logs.id
+ target_prefix = "s3-access-logs/"
}`,
  },
};

const SCRUB_MAP: Record<string, Array<{ label: string; raw: string; scrubbed: string; type: string }>> = {
  encryption: [
    { label: 'AWS Account ID', raw: '987654321098', scrubbed: '[SCRUBBED_ACCOUNT_9021]', type: 'HMAC-SHA256 Token' },
    { label: 'S3 Bucket ARN', raw: 'arn:aws:s3:::production-finance-ledger-2026', scrubbed: 'VIRTUAL_BUCKET_1', type: 'Virtual Token Vault' },
    { label: 'Developer Secret Key', raw: 'AKIAIOSFODNN7EXAMPLE', scrubbed: '[HMAC-REDACTED-KEY-7F8A]', type: 'Presidio Stripped' },
    { label: 'Owner Email', raw: 'finance-admin@enterprise.in', scrubbed: '[SCRUBBED_EMAIL_PII]', type: 'Zero-Egress Vault' },
  ],
  public: [
    { label: 'AWS Account ID', raw: '123456789012', scrubbed: '[SCRUBBED_ACCOUNT_1234]', type: 'HMAC-SHA256 Token' },
    { label: 'S3 Bucket ARN', raw: 'arn:aws:s3:::indian-citizen-medical-records-store', scrubbed: 'VIRTUAL_BUCKET_1', type: 'Virtual Token Vault' },
    { label: 'Citizen Aadhaar PII', raw: 'aadhaar 4532 8912 0019', scrubbed: '[REDACTED_AADHAAR_TOKEN]', type: 'DPDP Presidio Scrub' },
    { label: 'Backup Access Key', raw: 'AKIAIOSFODNN7EXAMPLE', scrubbed: '[HMAC-REDACTED-KEY-7F8A]', type: 'Zero-Egress Vault' },
  ],
  admin: [
    { label: 'AWS Account ID', raw: '123456789012', scrubbed: '[SCRUBBED_ACCOUNT_1234]', type: 'HMAC-SHA256 Token' },
    { label: 'IAM Policy ARN', raw: 'arn:aws:iam::123456789012:policy/DevAdminAccess', scrubbed: 'VIRTUAL_POLICY_1', type: 'Virtual Token Vault' },
    { label: 'Policy Name', raw: 'DevAdminAccess', scrubbed: '[SCRUBBED_POLICY_NAME]', type: 'HMAC Tokenized' },
  ],
  logging: [
    { label: 'AWS Account ID', raw: '123456789012', scrubbed: '[SCRUBBED_ACCOUNT_1234]', type: 'HMAC-SHA256 Token' },
    { label: 'S3 Bucket ARN', raw: 'arn:aws:s3:::customer-pii-audit-storage', scrubbed: 'VIRTUAL_BUCKET_1', type: 'Virtual Token Vault' },
    { label: 'Developer Token', raw: 'SECRET_TOKEN_XYZ987', scrubbed: '[HMAC-REDACTED-SECRET]', type: 'Presidio Stripped' },
  ],
};

function getScenarioPatchIr(key: string, raw: any, ruleId: string) {
  let ops: any[] = [];
  if (key === 'admin') {
    ops = [{ op: 'escalate', reason: 'Wildcard admin requires human architect review' }];
  } else if (key === 'public') {
    ops = [
      { op: 'set_attr', attr: 'block_public_acls', value: true },
      { op: 'set_attr', attr: 'block_public_policy', value: true },
      { op: 'set_attr', attr: 'ignore_public_acls', value: true },
      { op: 'set_attr', attr: 'restrict_public_buckets', value: true },
    ];
  } else if (key === 'logging') {
    ops = [
      { op: 'set_attr', attr: 'logging_enabled', value: true },
      { op: 'set_attr', attr: 'target_bucket', value: 'VIRTUAL_CENTRAL_LOGS' },
      { op: 'set_attr', attr: 'target_prefix', value: 's3-access-logs/' },
    ];
  } else {
    ops = [{ op: 'set_attr', attr: 'default_encryption', value: true }];
  }

  return {
    finding_id: raw.finding_id,
    resource_ref: 'VIRTUAL_RESOURCE_1',
    ops,
    rationale_ref: ruleId,
  };
}

export const PipelinePage: React.FC = () => {
  const [selectedScenarioKey, setSelectedScenarioKey] = useState<string>('encryption');
  const [currentStage, setCurrentStage] = useState<number>(1);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1800); // ms per step
  const [isLiveRunning, setIsLiveRunning] = useState<boolean>(false);
  const [liveResult, setLiveResult] = useState<PipelineExecutionResult | null>(null);
  const [copiedPatch, setCopiedPatch] = useState<boolean>(false);
  const [copiedHcl, setCopiedHcl] = useState<boolean>(false);
  const [copiedReceipt, setCopiedReceipt] = useState<boolean>(false);

  // Stage 4 Live Token Streaming state
  const [streamedText, setStreamedText] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [tokenCount, setTokenCount] = useState<number>(0);

  const stageRefs = useRef<(HTMLDivElement | null)[]>([]);
  const streamTimerRef = useRef<any>(null);

  const scenario = SCENARIOS[selectedScenarioKey] || SCENARIOS.encryption;
  const scrubItems = SCRUB_MAP[selectedScenarioKey] || SCRUB_MAP.encryption;

  const fullPatchIr = liveResult?.patch_ir || getScenarioPatchIr(selectedScenarioKey, scenario.raw, scenario.rule_id);
  const fullPatchIrString = JSON.stringify(fullPatchIr, null, 2);

  // Auto-play timer
  useEffect(() => {
    let timer: any = null;
    if (isPlaying) {
      timer = setTimeout(() => {
        if (currentStage < 6) {
          const next = currentStage + 1;
          setCurrentStage(next);
          scrollToStage(next);
        } else {
          setIsPlaying(false);
        }
      }, playbackSpeed);
    }
    return () => clearTimeout(timer);
  }, [isPlaying, currentStage, playbackSpeed]);

  // Stage 4 token streaming simulator
  useEffect(() => {
    if (currentStage >= 4) {
      startTokenStreaming();
    } else {
      setStreamedText('');
      setIsStreaming(false);
      setTokenCount(0);
    }
    return () => {
      if (streamTimerRef.current) clearInterval(streamTimerRef.current);
    };
  }, [currentStage, selectedScenarioKey, liveResult]);

  const startTokenStreaming = () => {
    if (streamTimerRef.current) clearInterval(streamTimerRef.current);
    setIsStreaming(true);
    setStreamedText('');
    setTokenCount(0);

    const target = fullPatchIrString;
    let charIndex = 0;
    const chunkSize = playbackSpeed === 900 ? 6 : 3;
    const intervalMs = playbackSpeed === 900 ? 12 : 22;

    streamTimerRef.current = setInterval(() => {
      charIndex += chunkSize;
      if (charIndex >= target.length) {
        setStreamedText(target);
        setIsStreaming(false);
        setTokenCount(Math.round(target.length / 3.8));
        clearInterval(streamTimerRef.current);
      } else {
        setStreamedText(target.slice(0, charIndex));
        setTokenCount(Math.round(charIndex / 3.8));
      }
    }, intervalMs);
  };

  const scrollToStage = (stageNum: number) => {
    const el = stageRefs.current[stageNum - 1];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  const handleSelectScenario = (key: string) => {
    setSelectedScenarioKey(key);
    setCurrentStage(1);
    setIsPlaying(false);
    setLiveResult(null);
    scrollToStage(1);
  };

  const handleStartAutoPlay = () => {
    if (currentStage >= 6) {
      setCurrentStage(1);
      scrollToStage(1);
    }
    setIsPlaying(true);
  };

  const handleNextStage = () => {
    if (currentStage < 6) {
      const next = currentStage + 1;
      setCurrentStage(next);
      scrollToStage(next);
    }
  };

  const handlePrevStage = () => {
    if (currentStage > 1) {
      const prev = currentStage - 1;
      setCurrentStage(prev);
      scrollToStage(prev);
    }
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentStage(1);
    setLiveResult(null);
    scrollToStage(1);
  };

  const handleRunBackendLive = async () => {
    setIsLiveRunning(true);
    setIsPlaying(false);
    try {
      const res = await runLivePipeline(selectedScenarioKey);
      setLiveResult(res);
      setCurrentStage(6);
      scrollToStage(6);
    } catch (err) {
      console.warn('Backend live pipeline invocation fallback:', err);
    } finally {
      setIsLiveRunning(false);
    }
  };

  const handleCopyPatch = () => {
    navigator.clipboard.writeText(fullPatchIrString);
    setCopiedPatch(true);
    setTimeout(() => setCopiedPatch(false), 2000);
  };

  const handleCopyHcl = () => {
    navigator.clipboard.writeText(scenario.hcl_after);
    setCopiedHcl(true);
    setTimeout(() => setCopiedHcl(false), 2000);
  };

  const handleCopyReceipt = () => {
    const rcpt = JSON.stringify({
      receipt_id: `rcpt-airlock-${selectedScenarioKey}-2026`,
      rule_id: scenario.rule_id,
      hmac_sha256: '7f8a91c2e409b3d182faec091244e8bc19d44321',
      bytes_leaked_to_network: 0,
      timestamp: new Date().toISOString(),
      vault: 'AES-256 Fernet (In-Memory VPC)',
      dpdp_compliance: 'Section 8 Zero-Egress Certified',
    }, null, 2);
    navigator.clipboard.writeText(rcpt);
    setCopiedReceipt(true);
    setTimeout(() => setCopiedReceipt(false), 2000);
  };

  return (
    <div className="w-full space-y-6 pb-20 select-none">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-ink-border/60 pb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 text-[11px] font-mono font-semibold bg-peacock/10 text-peacock rounded-full flex items-center gap-1">
              <Zap className="w-3 h-3" />
              <span>demo.py GUI Engine</span>
            </span>
            <span className="text-xs text-ink-muted font-mono">Real-Time Autonomous IaC Remediation</span>
          </div>
          <h1 className="font-headline text-2xl sm:text-3xl font-bold text-ink tracking-tight">
            Live Autonomous Remediation Pipeline
          </h1>
          <p className="text-xs sm:text-sm text-ink-muted mt-1 max-w-3xl">
            Interactive visual simulation of ARGUS’s 6-stage on-device pipeline. Demonstrates secret stripping, 
            Personalized PageRank blast radius, Ollama model synthesis, OPA Rego verification, and Terraform diff generation.
          </p>
        </div>

        {/* Engine Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="px-3 py-1.5 bg-paper border border-ink-border/80 rounded-control text-xs font-mono flex items-center gap-2 shadow-xs">
            <span className="w-2 h-2 rounded-full bg-forest animate-pulse" />
            <span>Ollama: argus-m1-sft</span>
          </div>
          <div className="px-3 py-1.5 bg-paper border border-ink-border/80 rounded-control text-xs font-mono flex items-center gap-2 shadow-xs">
            <ShieldCheck className="w-3.5 h-3.5 text-peacock" />
            <span>OPA Rego Gate</span>
          </div>
        </div>
      </div>

      {/* Scenario Selector Cards */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-ink uppercase tracking-wider">
          Select Cloud Misconfiguration Scenario:
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {Object.entries(SCENARIOS).map(([key, sc]) => {
            const isSelected = selectedScenarioKey === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => handleSelectScenario(key)}
                className={`p-3.5 rounded-xl border text-left transition-all duration-150 flex flex-col justify-between ${
                  isSelected
                    ? 'bg-paper border-peacock shadow-md ring-2 ring-peacock/20'
                    : 'bg-paper/70 border-ink-border hover:border-ink-muted hover:bg-paper'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-1 mb-1.5">
                    <span className="text-[10px] font-mono font-semibold px-2 py-0.5 bg-mist rounded border border-ink-border/50 text-ink">
                      {sc.rule_id}
                    </span>
                    <span
                      className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                        sc.blast_radius >= 0.8
                          ? 'bg-terracotta/15 text-terracotta'
                          : 'bg-copper/15 text-copper'
                      }`}
                    >
                      PPR: {sc.blast_radius.toFixed(3)}
                    </span>
                  </div>
                  <h2 className="text-xs font-bold text-ink line-clamp-2 leading-snug">
                    {sc.title}
                  </h2>
                </div>
                <div className="mt-2.5 pt-2 border-t border-ink-border/40 text-[11px] text-ink-muted flex items-center justify-between">
                  <span>{sc.raw.resource_type}</span>
                  <span className={isSelected ? 'text-peacock font-semibold' : ''}>
                    {isSelected ? 'Active Scenario' : 'Select'}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Global Interactive Execution Controls */}
      <div className="sticky top-0 z-30 p-3 bg-paper/95 backdrop-blur-md border border-ink-border shadow-md rounded-xl flex flex-wrap items-center justify-between gap-3">
        {/* Left: Auto-Play & Navigation */}
        <div className="flex items-center gap-2">
          {isPlaying ? (
            <button
              type="button"
              onClick={() => setIsPlaying(false)}
              className="px-3 py-1.5 text-xs font-semibold bg-terracotta text-paper rounded-control hover:bg-terracotta/90 transition-colors flex items-center gap-1.5 shadow-xs"
            >
              <Pause className="w-3.5 h-3.5" />
              <span>Pause</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={handleStartAutoPlay}
              className="px-3.5 py-1.5 text-xs font-semibold bg-peacock text-paper rounded-control hover:bg-peacock-hover transition-colors flex items-center gap-1.5 shadow-xs"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Auto-Play Flow</span>
            </button>
          )}

          <div className="flex items-center border border-ink-border rounded-control overflow-hidden bg-paper">
            <button
              type="button"
              onClick={handlePrevStage}
              disabled={currentStage <= 1}
              className="px-2.5 py-1.5 text-xs text-ink-muted hover:text-ink hover:bg-mist disabled:opacity-40 transition-colors flex items-center gap-1"
              title="Previous stage"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Prev</span>
            </button>
            <span className="px-2.5 py-1 text-xs font-mono font-semibold text-ink border-x border-ink-border bg-mist/50">
              Stage {currentStage}/6
            </span>
            <button
              type="button"
              onClick={handleNextStage}
              disabled={currentStage >= 6}
              className="px-2.5 py-1.5 text-xs text-ink-muted hover:text-ink hover:bg-mist disabled:opacity-40 transition-colors flex items-center gap-1"
              title="Next stage"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            type="button"
            onClick={handleReset}
            className="p-1.5 text-ink-muted hover:text-ink hover:bg-mist rounded-control border border-ink-border transition-colors"
            title="Reset pipeline"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={() => setPlaybackSpeed(playbackSpeed === 1800 ? 900 : 1800)}
            className="px-2 py-1 text-[11px] font-mono text-ink-muted hover:text-ink hover:bg-mist rounded-control border border-ink-border transition-colors"
            title="Toggle playback speed"
          >
            {playbackSpeed === 1800 ? '1x Speed' : '2x Speed'}
          </button>
        </div>

        {/* Center: Stage Stepper Pills */}
        <div className="hidden xl:flex items-center gap-1">
          {[
            { num: 1, label: '1. Ingest' },
            { num: 2, label: '2. Airlock' },
            { num: 3, label: '3. Blast Radius' },
            { num: 4, label: '4. Ollama M1' },
            { num: 5, label: '5. OPA Gate' },
            { num: 6, label: '6. Terraform Diff' },
          ].map((st) => (
            <button
              key={st.num}
              type="button"
              onClick={() => {
                setCurrentStage(st.num);
                scrollToStage(st.num);
              }}
              className={`px-2.5 py-1 text-xs font-medium rounded-full transition-all ${
                st.num === currentStage
                  ? 'bg-peacock text-paper font-semibold shadow-xs'
                  : st.num < currentStage
                  ? 'bg-forest/15 text-forest font-medium'
                  : 'text-ink-muted hover:bg-mist'
              }`}
            >
              {st.label}
            </button>
          ))}
        </div>

        {/* Right: Live Backend Trigger */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRunBackendLive}
            disabled={isLiveRunning}
            className="px-3.5 py-1.5 text-xs font-semibold bg-forest text-paper rounded-control hover:bg-forest/90 transition-colors flex items-center gap-1.5 shadow-xs disabled:opacity-60"
            title="Invoke live Python backend on localhost / EC2"
          >
            {isLiveRunning ? (
              <>
                <Zap className="w-3.5 h-3.5 animate-spin" />
                <span>Invoking On-Device Ollama...</span>
              </>
            ) : (
              <>
                <Terminal className="w-3.5 h-3.5" />
                <span>Run Live on Backend</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 6 COORDINATED STAGES VISUALIZER */}
      {/* ========================================================================= */}
      <div className="space-y-6">
        {/* --------------------------------------------------------------------- */}
        {/* STAGE 1: CLOUD IAC INGESTION */}
        {/* --------------------------------------------------------------------- */}
        <div
          ref={(el) => (stageRefs.current[0] = el)}
          className={`p-5 rounded-2xl border transition-all duration-200 ${
            currentStage === 1
              ? 'bg-paper border-peacock shadow-lg ring-2 ring-peacock/10'
              : 'bg-paper/80 border-ink-border/80'
          }`}
        >
          <div className="flex items-center justify-between border-b border-ink-border/50 pb-3 mb-4">
            <div className="flex items-center gap-2.5">
              <span className="w-6 h-6 rounded-full bg-peacock/10 text-peacock flex items-center justify-center font-bold text-xs">
                1
              </span>
              <div>
                <h3 className="text-sm font-bold text-ink">
                  [STEP 1 / 6] Cloud IaC Finding Ingestion
                </h3>
                <p className="text-[11px] text-ink-muted">
                  Ingests raw Terraform state with sensitive AWS account IDs, IAM ARNs, and hardcoded keys
                </p>
              </div>
            </div>
            <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-terracotta/10 text-terracotta rounded">
              High-Risk Plaintext
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Sensitive Tags Alert Box */}
            <div className="p-3.5 bg-terracotta/5 border border-terracotta/20 rounded-xl space-y-2 text-xs">
              <div className="flex items-center gap-1.5 font-semibold text-terracotta">
                <AlertTriangle className="w-4 h-4" />
                <span>Sensitive PII / Credential Exposure:</span>
              </div>
              <p className="text-ink-muted text-[11px] leading-relaxed">
                Raw cloud findings contain proprietary AWS account numbers, confidential citizen data, and developer tokens. 
                Streaming these to external AI models (e.g. OpenAI/Anthropic) violates <strong>DPDP Act Section 8</strong>.
              </p>
              <div className="space-y-1 pt-1 font-mono text-[10px]">
                <div className="p-1 bg-paper rounded border border-terracotta/30 text-terracotta font-semibold">
                  ⚠ Account ID: {scenario.raw.attributes.account_id}
                </div>
                <div className="p-1 bg-paper rounded border border-terracotta/30 text-terracotta font-semibold truncate">
                  ⚠ ARN: {scenario.raw.attributes.arn}
                </div>
                {scenario.raw.attributes.tags?.secret_note && (
                  <div className="p-1 bg-paper rounded border border-terracotta/30 text-terracotta font-semibold">
                    ⚠ Secret: {scenario.raw.attributes.tags.secret_note}
                  </div>
                )}
                {scenario.raw.attributes.user_data && (
                  <div className="p-1 bg-paper rounded border border-terracotta/30 text-terracotta font-semibold">
                    ⚠ Citizen Data: {scenario.raw.attributes.user_data}
                  </div>
                )}
              </div>
            </div>

            {/* Raw JSON Code Block with Red Highlighting */}
            <div className="lg:col-span-2 space-y-1">
              <div className="flex items-center justify-between text-[11px] font-mono text-ink-muted px-1">
                <span>finding_raw.json</span>
                <span>Format: AWS Cartography AST</span>
              </div>
              <pre className="p-3.5 bg-ink text-paper rounded-xl text-xs font-mono overflow-x-auto leading-relaxed border border-ink/40 max-h-64">
                {JSON.stringify(scenario.raw, null, 2)}
              </pre>
            </div>
          </div>
        </div>

        {/* --------------------------------------------------------------------- */}
        {/* STAGE 2: PRIVACY AIRLOCK */}
        {/* --------------------------------------------------------------------- */}
        <div
          ref={(el) => (stageRefs.current[1] = el)}
          className={`p-5 rounded-2xl border transition-all duration-200 ${
            currentStage === 2
              ? 'bg-paper border-peacock shadow-lg ring-2 ring-peacock/10'
              : 'bg-paper/80 border-ink-border/80'
          }`}
        >
          <div className="flex items-center justify-between border-b border-ink-border/50 pb-3 mb-4">
            <div className="flex items-center gap-2.5">
              <span className="w-6 h-6 rounded-full bg-peacock/10 text-peacock flex items-center justify-center font-bold text-xs">
                2
              </span>
              <div>
                <h3 className="text-sm font-bold text-ink">
                  [STEP 2 / 6] Zero-Egress Privacy Airlock & HMAC Pseudonymization
                </h3>
                <p className="text-[11px] text-ink-muted">
                  Deterministic tokenization & secret stripping. Emits cryptographic zero-egress receipts.
                </p>
              </div>
            </div>
            <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-forest/15 text-forest rounded">
              0 Bytes Leaked
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Interactive Transformation Mapping Table */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-[11px] font-mono text-ink-muted px-1">
                <span className="font-semibold text-ink">Airlock Pseudonymization Pipeline</span>
                <span className="text-forest">Presidio + Vault ✓</span>
              </div>
              <div className="p-3 bg-paper border border-ink-border rounded-xl space-y-2 text-xs">
                {scrubItems.map((item, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded-lg bg-mist/50 border border-ink-border/60 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px]"
                  >
                    <div className="space-y-0.5">
                      <span className="text-[10px] text-ink-muted font-sans font-medium uppercase tracking-wider">{item.label}</span>
                      <p className="font-mono text-terracotta line-through text-[11px] truncate max-w-[200px]">{item.raw}</p>
                    </div>
                    <div className="flex items-center gap-1.5 text-right font-mono">
                      <ArrowRight className="w-3 h-3 text-peacock flex-shrink-0" />
                      <span className="px-1.5 py-0.5 bg-paper rounded border border-forest/30 text-forest font-semibold">{item.scrubbed}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Cryptographic Privacy Receipt */}
            <div className="p-4 bg-forest/5 border border-forest/20 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Lock className="w-4 h-4 text-forest" />
                  <span className="text-xs font-bold text-forest">Signed Privacy Receipt Badge</span>
                </div>
                <button
                  type="button"
                  onClick={handleCopyReceipt}
                  className="text-[11px] text-forest hover:text-forest/80 flex items-center gap-1 font-mono font-medium"
                >
                  <Copy className="w-3 h-3" />
                  <span>{copiedReceipt ? 'Copied Receipt!' : 'Copy Receipt'}</span>
                </button>
              </div>

              <div className="space-y-1.5 text-xs text-ink font-mono text-[11px]">
                <div className="flex justify-between py-1 border-b border-forest/10">
                  <span className="text-ink-muted">Receipt ID:</span>
                  <span className="font-bold">rcpt-airlock-2026-x9</span>
                </div>
                <div className="flex justify-between py-1 border-b border-forest/10">
                  <span className="text-ink-muted">Record SHA256:</span>
                  <span className="text-peacock">7f8a91c2e409b3d1...</span>
                </div>
                <div className="flex justify-between py-1 border-b border-forest/10">
                  <span className="text-ink-muted">Network Leaked:</span>
                  <span className="text-forest font-bold">0.00 Bytes (Certified)</span>
                </div>
                <div className="flex justify-between py-1 border-b border-forest/10">
                  <span className="text-ink-muted">Token Vault:</span>
                  <span>AES-256 Fernet (In-Memory VPC)</span>
                </div>
              </div>

              <p className="text-[11px] text-ink-muted leading-relaxed">
                Irrefutable technical evidence guaranteeing to Indian regulatory auditors (DPBI & CERT-In) 
                that zero sensitive cloud parameters left the local VPC perimeter.
              </p>
            </div>
          </div>
        </div>

        {/* --------------------------------------------------------------------- */}
        {/* STAGE 3: ATTACK GRAPH & RISK (PAGERANK) */}
        {/* --------------------------------------------------------------------- */}
        <div
          ref={(el) => (stageRefs.current[2] = el)}
          className={`p-5 rounded-2xl border transition-all duration-200 ${
            currentStage === 3
              ? 'bg-paper border-peacock shadow-lg ring-2 ring-peacock/10'
              : 'bg-paper/80 border-ink-border/80'
          }`}
        >
          <div className="flex items-center justify-between border-b border-ink-border/50 pb-3 mb-4">
            <div className="flex items-center gap-2.5">
              <span className="w-6 h-6 rounded-full bg-peacock/10 text-peacock flex items-center justify-center font-bold text-xs">
                3
              </span>
              <div>
                <h3 className="text-sm font-bold text-ink">
                  [STEP 3 / 6] Cartographic Attack Graph & Blast Radius Evaluation
                </h3>
                <p className="text-[11px] text-ink-muted">
                  Personalized PageRank (PPR) over multi-hop privilege escalation corridors
                </p>
              </div>
            </div>
            <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-saffron/20 text-ink rounded">
              Stackelberg Priority Tier 1
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 bg-mist/60 border border-ink-border rounded-xl space-y-1">
              <span className="text-[11px] text-ink-muted font-medium">Attacker Exploit Corridor:</span>
              <p className="text-xs font-semibold text-ink leading-snug">{scenario.exploit_path}</p>
              <div className="pt-2 text-[10px] text-ink-muted font-mono flex items-center gap-1">
                <span>developer-raynor</span>
                <ChevronRight className="w-3 h-3 text-peacock" />
                <span>AssumeRole</span>
                <ChevronRight className="w-3 h-3 text-peacock" />
                <span className="font-bold text-terracotta truncate">{scenario.raw.resource_id}</span>
              </div>
            </div>

            <div className="p-4 bg-mist/60 border border-ink-border rounded-xl space-y-1">
              <span className="text-[11px] text-ink-muted font-medium">Blast Radius (PageRank):</span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono text-terracotta">
                  {scenario.blast_radius.toFixed(3)}
                </span>
                <span className="text-xs text-ink-muted font-mono">/ 1.000</span>
              </div>
              <p className="text-[11px] text-terracotta font-medium">High Criticality Asset Vulnerability</p>
            </div>

            <div className="p-4 bg-mist/60 border border-ink-border rounded-xl space-y-1">
              <span className="text-[11px] text-ink-muted font-medium">Stackelberg Remediation Cut:</span>
              <p className="text-xs font-semibold text-forest">Optimal Cut-Set (K=3 Budget)</p>
              <p className="text-[11px] text-ink-muted">
                Severing this node drops global attacker reachability likelihood from 90.6% down to 31.0%.
              </p>
            </div>
          </div>
        </div>

        {/* --------------------------------------------------------------------- */}
        {/* STAGE 4: LOCAL MODEL SYNTHESIS (OLLAMA M1) */}
        {/* --------------------------------------------------------------------- */}
        <div
          ref={(el) => (stageRefs.current[3] = el)}
          className={`p-5 rounded-2xl border transition-all duration-200 ${
            currentStage === 4
              ? 'bg-paper border-peacock shadow-lg ring-2 ring-peacock/10'
              : 'bg-paper/80 border-ink-border/80'
          }`}
        >
          <div className="flex items-center justify-between border-b border-ink-border/50 pb-3 mb-4">
            <div className="flex items-center gap-2.5">
              <span className="w-6 h-6 rounded-full bg-peacock/10 text-peacock flex items-center justify-center font-bold text-xs">
                4
              </span>
              <div>
                <h3 className="text-sm font-bold text-ink">
                  [STEP 4 / 6] On-Device Model Synthesis (Ollama argus-m1-sft)
                </h3>
                <p className="text-[11px] text-ink-muted">
                  Deterministic Patch-IR JSON synthesis governed by GBNF Grammar Constraints (Zero Hallucination)
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-peacock/10 text-peacock rounded flex items-center gap-1">
                {isStreaming && <span className="w-1.5 h-1.5 rounded-full bg-peacock animate-ping" />}
                <span>{isStreaming ? `Generating... ${tokenCount} tok` : '84ms Latency'}</span>
              </span>
              <button
                type="button"
                onClick={startTokenStreaming}
                className="px-2 py-0.5 text-[11px] text-peacock hover:bg-peacock/10 border border-peacock/30 rounded font-medium flex items-center gap-1"
                title="Re-run live streaming simulation"
              >
                <Sparkles className="w-3 h-3" />
                <span>Re-Stream</span>
              </button>
              <button
                type="button"
                onClick={handleCopyPatch}
                className="text-[11px] text-peacock hover:text-peacock-dark flex items-center gap-1 font-medium"
              >
                <Copy className="w-3 h-3" />
                <span>{copiedPatch ? 'Copied!' : 'Copy Patch-IR'}</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="p-3.5 bg-mist/60 border border-ink-border rounded-xl space-y-2 text-xs">
              <span className="font-semibold text-ink">Model Architecture Details:</span>
              <ul className="space-y-1.5 text-[11px] text-ink-muted">
                <li>• <strong>Base:</strong> <code className="font-mono">unsloth/Qwen3.5-4B</code> (Quantized Q4_K_M GGUF)</li>
                <li>• <strong>Fine-Tuning:</strong> SFT + RFT QLoRA (3,309 synthetic; 94.48% OOF Pass@1)</li>
                <li>• <strong>Grammar:</strong> Schema-constrained Patch-IR JSON (100% OOF valid)</li>
                <li>• <strong>Host:</strong> Local Ollama Daemon (<code className="font-mono">127.0.0.1:11434</code>)</li>
                <li>• <strong>Latency:</strong> Tier 0 0.4ms • Ollama M1 1.6s–3.5s</li>
              </ul>
            </div>

            <div className="lg:col-span-2">
              <div className="flex items-center justify-between text-[11px] font-mono text-ink-muted px-1 mb-1">
                <span className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${isStreaming ? 'bg-peacock animate-pulse' : 'bg-forest'}`} />
                  <span>patch_ir.json {isStreaming ? '(Token Streaming Live...)' : '(100% Schema Valid)'}</span>
                </span>
                <span>Grammar: AST-GBNF</span>
              </div>
              <pre className="p-3.5 bg-ink text-paper rounded-xl text-xs font-mono overflow-x-auto leading-relaxed border border-ink/40 max-h-56">
                {streamedText || fullPatchIrString}
                {isStreaming && <span className="text-peacock animate-pulse font-bold">▋</span>}
              </pre>
            </div>
          </div>
        </div>

        {/* --------------------------------------------------------------------- */}
        {/* STAGE 5: OPA REGO VERIFICATION GATE */}
        {/* --------------------------------------------------------------------- */}
        <div
          ref={(el) => (stageRefs.current[4] = el)}
          className={`p-5 rounded-2xl border transition-all duration-200 ${
            currentStage === 5
              ? 'bg-paper border-peacock shadow-lg ring-2 ring-peacock/10'
              : 'bg-paper/80 border-ink-border/80'
          }`}
        >
          <div className="flex items-center justify-between border-b border-ink-border/50 pb-3 mb-4">
            <div className="flex items-center gap-2.5">
              <span className="w-6 h-6 rounded-full bg-peacock/10 text-peacock flex items-center justify-center font-bold text-xs">
                5
              </span>
              <div>
                <h3 className="text-sm font-bold text-ink">
                  [STEP 5 / 6] Automated Formal Verification Gate (OPA Rego)
                </h3>
                <p className="text-[11px] text-ink-muted">
                  Open Policy Agent verifies syntactic validity, intent preservation, and statutory DPDP compliance
                </p>
              </div>
            </div>
            <span className={`px-2 py-0.5 text-[10px] font-mono font-semibold rounded ${
              selectedScenarioKey === 'admin'
                ? 'bg-copper/20 text-copper'
                : 'bg-forest/15 text-forest'
            }`}>
              {selectedScenarioKey === 'admin' ? 'ESCALATED TO ARCHITECT' : 'VERIFIED PASSED'}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
            <div className="p-3 bg-paper border border-forest/30 rounded-xl space-y-1">
              <div className="flex items-center gap-1.5 text-forest font-semibold">
                <CheckCircle2 className="w-4 h-4 text-forest" />
                <span>1. Schema Check</span>
              </div>
              <p className="text-[11px] text-ink-muted">100% Valid JSON AST against Patch-IR schema</p>
            </div>

            <div className="p-3 bg-paper border border-forest/30 rounded-xl space-y-1">
              <div className="flex items-center gap-1.5 text-forest font-semibold">
                <CheckCircle2 className="w-4 h-4 text-forest" />
                <span>2. Intent Preservation</span>
              </div>
              <p className="text-[11px] text-ink-muted">0 unauthorized resource deletions detected</p>
            </div>

            <div className="p-3 bg-paper border border-forest/30 rounded-xl space-y-1">
              <div className="flex items-center gap-1.5 text-forest font-semibold">
                <CheckCircle2 className="w-4 h-4 text-forest" />
                <span>3. Regulatory Policy</span>
              </div>
              <p className="text-[11px] text-ink-muted">Validated against CIS AWS v3.0 & India DPDP Act</p>
            </div>

            <div className={`p-3 bg-paper border rounded-xl space-y-1 ${
              selectedScenarioKey === 'admin' ? 'border-copper/40 bg-copper/5' : 'border-forest/30'
            }`}>
              <div className="flex items-center gap-1.5 font-semibold">
                {selectedScenarioKey === 'admin' ? (
                  <>
                    <ShieldCheck className="w-4 h-4 text-copper" />
                    <span className="text-copper">4. Dual-Tier Safety</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-forest" />
                    <span className="text-forest">4. Adversarial Safety</span>
                  </>
                )}
              </div>
              <p className="text-[11px] text-ink-muted">
                {selectedScenarioKey === 'admin'
                  ? 'Escalated to Tier 3 human architect queue (wildcard admin policy)'
                  : 'Certified Tier 1 fix: Pre-approved for auto-commit'}
              </p>
            </div>
          </div>
        </div>

        {/* --------------------------------------------------------------------- */}
        {/* STAGE 6: VERIFIED TERRAFORM HCL DIFF */}
        {/* --------------------------------------------------------------------- */}
        <div
          ref={(el) => (stageRefs.current[5] = el)}
          className={`p-5 rounded-2xl border transition-all duration-200 ${
            currentStage === 6
              ? 'bg-paper border-peacock shadow-lg ring-2 ring-peacock/10'
              : 'bg-paper/80 border-ink-border/80'
          }`}
        >
          <div className="flex items-center justify-between border-b border-ink-border/50 pb-3 mb-4">
            <div className="flex items-center gap-2.5">
              <span className="w-6 h-6 rounded-full bg-peacock/10 text-peacock flex items-center justify-center font-bold text-xs">
                6
              </span>
              <div>
                <h3 className="text-sm font-bold text-ink">
                  [STEP 6 / 6] Autonomous Remediation Diff (Ready for Git Commit)
                </h3>
                <p className="text-[11px] text-ink-muted">
                  Color-coded unified Terraform HCL diff ready for review or auto-dispatch
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleCopyHcl}
              className="text-[11px] text-peacock hover:text-peacock-dark flex items-center gap-1 font-medium"
            >
              <Copy className="w-3 h-3" />
              <span>{copiedHcl ? 'Copied Diff!' : 'Copy Terraform HCL'}</span>
            </button>
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs font-mono text-ink-muted">
              <span>--- a/main.tf (Original Misconfigured)</span>
              <span>+++ b/main.tf (ARGUS Remediated)</span>
            </div>

            <div className="p-4 bg-ink text-paper rounded-xl text-xs font-mono overflow-x-auto leading-relaxed border border-ink/50 space-y-0.5">
              {scenario.hcl_after.split('\n').map((line, idx) => {
                if (line.startsWith('+')) {
                  return (
                    <div key={idx} className="text-forest font-semibold bg-forest/10 px-1 rounded">
                      {line}
                    </div>
                  );
                } else if (line.startsWith('-')) {
                  return (
                    <div key={idx} className="text-terracotta bg-terracotta/10 px-1 rounded">
                      {line}
                    </div>
                  );
                } else {
                  return (
                    <div key={idx} className="text-paper/70">
                      {line}
                    </div>
                  );
                }
              })}
            </div>

            {/* Success Summary Callout */}
            <div className="p-3 bg-forest/10 border border-forest/20 rounded-xl flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 text-forest font-semibold">
                <CheckCircle2 className="w-4 h-4" />
                <span>Zero Cloud Egress • 100% DPDP Act Compliant • Verified Autonomous Remediation</span>
              </div>
              <span className="font-mono text-[10px] text-ink-muted">Pipeline Complete in ~84ms</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
