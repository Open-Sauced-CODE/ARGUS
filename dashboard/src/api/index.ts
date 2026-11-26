import {
  GraphPayload,
  iamFindings,
  iamComp,
  iamRem,
  PrivacyReceipt,
  OverviewPayload,
  ArchitecturePayload,
  PipelineExecutionResult,
  TenantInfo,
  TenantConnectPayload,
  HealthPayload,
  LocalStatusPayload,
  ReleasesPayload,
  BenchmarksPayload,
  DocsPayload,
  ScanResultPayload,
  DiscoveredGguf,
  OllamaPullStatus,
} from '../types';

import { useFindingsStore } from '../store/findingsStore';
import { useWorkspaceStore } from '../store/workspaceStore';
import rawGraph from '../mock/mockGraph.json';
import rawCompliance from '../mock/mockCompliance.json';
import rawInterdiction from '../mock/mockInterdiction.json';
import rawOverview from '../mock/mockOverview.json';
import rawReceipts from '../mock/mockReceipts.json';
import rawUser from '../mock/mockUser.json';
import rawReleases from '../mock/mockReleases.json';
import rawBenchmarks from '../mock/mockBenchmarks.json';

export function getApiBase(): string {
  const { runtimeTarget, localEngineUrl, serverHealth } = useWorkspaceStore.getState();
  if (serverHealth?.runtime_mode === 'local_agent') {
    return '';
  }
  if (runtimeTarget === 'local' && typeof window !== 'undefined') {
    const { hostname, port } = window.location;
    const isAlreadyLocal = (hostname === '127.0.0.1' || hostname === 'localhost') && port === '8742';
    if (!isAlreadyLocal) {
      return localEngineUrl.replace(/\/+$/, '');
    }
  }
  return '';
}

async function safeFetch<T>(endpoint: string, fallback: () => T, options?: RequestInit): Promise<T> {
  const base = getApiBase();
  const isLocalTarget = useWorkspaceStore.getState().runtimeTarget === 'local';
  try {
    const res = await fetch(`${base}${endpoint}`, {
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      ...options,
    });
    if (!res.ok) {
      if (isLocalTarget && base !== '') {
        let msg = `Local engine request ${endpoint} failed (${res.status})`;
        try {
          const errBody = await res.json();
          if (errBody?.error) msg = errBody.error;
        } catch {}
        throw new Error(msg);
      }
      console.warn(`API call ${endpoint} returned status ${res.status}, falling back.`);
      return fallback();
    }
    return (await res.json()) as T;
  } catch (err) {
    if (isLocalTarget && base !== '') {
      throw err;
    }
    return fallback();
  }
}

export function getInitialGraph(): GraphPayload {
  return JSON.parse(JSON.stringify(rawGraph));
}

export function getInitialCompliance(): iamComp[] {
  const allFindings = useFindingsStore.getState().findings;
  const baseRules: iamComp[] = JSON.parse(JSON.stringify(rawCompliance));

  // Dynamically calculate failing/violations count based on store state
  return baseRules.map((rule) => {
    if (rule.is_visibility_flag) return rule;
    const ruleFindingIds = rule.finding_ids || [];
    const activeViolations = allFindings.filter(
      (f) =>
        ruleFindingIds.includes(f.finding_id) &&
        f.auto_apply_status !== 'APPROVED' &&
        f.auto_apply_status !== 'APPLIED'
    ).length;

    return {
      ...rule,
      failing_count: activeViolations,
      violations_count: activeViolations,
    };
  });
}

export function getInitialInterdiction(budget = 3): iamRem {
  const clampedBudget = Math.max(0, Math.min(10, Math.round(budget)));
  const base = JSON.parse(JSON.stringify(rawInterdiction));
  const table = base.budget_table || {};
  const entry = table[String(clampedBudget)];

  if (entry) {
    const selectedFindings = entry.selected_fixes
      ? entry.selected_fixes.map((f: any) => f.finding_id)
      : [];

    return {
      budget: clampedBudget,
      baseline_likelihood: base.baseline_likelihood ?? 0.906,
      residual_likelihood: entry.residual_likelihood,
      selected_findings: selectedFindings,
      edges_interdicted: entry.edges_interdicted ?? [],
      cost_spent: entry.cost_spent ?? 0,
      attacker_shortest_path_cost: entry.attacker_shortest_path_cost ?? 1.2,
      baseline_path_cost: base.baseline_path_cost ?? 1.2,
      selected_fixes: entry.selected_fixes ?? [],
      pareto_curve: base.pareto_curve ?? [],
    };
  }

  // Fallback if not found
  return {
    budget: clampedBudget,
    baseline_likelihood: base.baseline_likelihood ?? 0.906,
    residual_likelihood: base.residual_likelihood ?? 0.586,
    selected_findings: base.selected_findings ?? [],
    edges_interdicted: base.edges_interdicted ?? [],
    cost_spent: base.cost_spent ?? 2,
    attacker_shortest_path_cost: base.attacker_shortest_path_cost ?? 5.8,
    baseline_path_cost: base.baseline_path_cost ?? 1.2,
    selected_fixes: [],
    pareto_curve: base.pareto_curve ?? [],
  };
}

const NUMBER_WORDS = [
  'Zero',
  'One',
  'Two',
  'Three',
  'Four',
  'Five',
  'Six',
  'Seven',
  'Eight',
  'Nine',
  'Ten',
];

export function getInitialOverview(budget = 3): OverviewPayload {
  const interdiction = getInitialInterdiction(budget);
  const compliance = getInitialCompliance();
  const approvals = useFindingsStore.getState().getPendingFindings();

  const k = interdiction.budget;
  const word = NUMBER_WORDS[k] || String(k);
  const totalReduction = interdiction.baseline_likelihood - interdiction.residual_likelihood;
  const topFixReduction = interdiction.selected_fixes?.[0]?.marginal_reduction ?? 0;

  let headline: string;
  if (k === 0) {
    headline = 'Select an interdiction budget to eliminate attack paths.';
  } else if (totalReduction > 0 && topFixReduction >= totalReduction / 2) {
    headline = 'One fix removes most of your exposure.';
  } else if (k === 1) {
    headline = 'One fix removes most of your exposure.';
  } else {
    headline = `${word} fixes remove most of your exposure.`;
  }

  const baselinePct = Math.round(interdiction.baseline_likelihood * 100);
  const residualPct = Math.round(interdiction.residual_likelihood * 100);
  const subline = `Modelled attack likelihood drops from ${baselinePct}% to ${residualPct}%.`;
  const waitingFindings = approvals.slice(0, 4);

  return {
    scan_id: rawOverview.scan_id,
    region: 'ap-south-1 (Mumbai, India)',
    scanned_time: rawOverview.scanned_time,
    is_on_device: true,
    user_name: (rawUser as any).name || 'Prabhav (SwasthyaPay Lead)',
    certified: false,
    headline,
    subline,
    action_button_label: 'Review interdiction plan',
    auto_apply_threshold_pct: 95,
    waiting_findings: waitingFindings,
    compliance,
    interdiction,
    pending_approvals_count: approvals.length,
    graph_summary: rawOverview.graph_summary,
  };
}

// -----------------------------------------------------------------------------
// ASYNCHRONOUS API CALLS WITH LIVE BACKEND CONNECTION & LOCAL FALLBACK
// -----------------------------------------------------------------------------

export async function getOverview(budget = 3): Promise<OverviewPayload> {
  return safeFetch(`/api/overview?budget=${budget}`, () => getInitialOverview(budget));
}

export async function getGraph(): Promise<GraphPayload> {
  return safeFetch('/api/graph', () => getInitialGraph());
}

export async function getFindings(): Promise<iamFindings[]> {
  const remote = await safeFetch<iamFindings[] | null>('/api/findings', () => null);
  if (remote && Array.isArray(remote)) {
    // Sync store with live backend state (including empty clean-scan arrays in local mode)
    useFindingsStore.setState({ findings: remote });
    return remote;
  }
  return useFindingsStore.getState().findings;
}

export async function getFinding(id: string): Promise<iamFindings | null> {
  const remote = await safeFetch<iamFindings | null>(`/api/findings/${id}`, () => null);
  if (remote) return remote;
  const finding = useFindingsStore.getState().findings.find((f) => f.finding_id === id);
  return finding ? JSON.parse(JSON.stringify(finding)) : null;
}

export async function getCompliance(): Promise<iamComp[]> {
  return safeFetch('/api/compliance', () => getInitialCompliance());
}

export async function getInterdiction(budget = 3): Promise<iamRem> {
  return safeFetch(`/api/interdiction?budget=${budget}`, () => getInitialInterdiction(budget));
}

export async function getApprovals(): Promise<iamFindings[]> {
  const remote = await safeFetch<iamFindings[] | null>('/api/approvals', () => null);
  if (remote && Array.isArray(remote)) {
    return remote;
  }
  return useFindingsStore.getState().getPendingFindings();
}

export async function approveFinding(id: string): Promise<{ success: boolean; finding?: iamFindings }> {
  const base = getApiBase();
  const { runtimeTarget, serverHealth, bumpWorkspaceRevision } = useWorkspaceStore.getState();
  const isLocalBackend = runtimeTarget === 'local' || serverHealth?.runtime_mode === 'local_agent';
  try {
    const res = await fetch(`${base}/api/approvals/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ finding_id: id }),
    });
    if (res.ok) {
      const data = await res.json();
      useFindingsStore.getState().approveFinding(id);
      bumpWorkspaceRevision();
      return { success: true, finding: data.finding };
    }
    if (isLocalBackend) {
      let msg = `Local approval failed (${res.status})`;
      try {
        const errBody = await res.json();
        if (errBody?.error) msg = errBody.error;
      } catch {}
      throw new Error(msg);
    }
  } catch (err) {
    if (isLocalBackend) {
      throw err;
    }
    console.warn('API approve failed, using local store:', err);
  }
  const fallback = useFindingsStore.getState().approveFinding(id);
  bumpWorkspaceRevision();
  return fallback;
}

export async function getReceipt(findingId: string): Promise<PrivacyReceipt | null> {
  const remote = await safeFetch<PrivacyReceipt | null>(`/api/receipts/${findingId}`, () => null);
  if (remote) return remote;
  const receipt = (rawReceipts as unknown as PrivacyReceipt[]).find(
    (r) => r.finding_id === findingId
  );
  return receipt ? JSON.parse(JSON.stringify(receipt)) : null;
}

export async function getReceipts(): Promise<PrivacyReceipt[]> {
  return safeFetch('/api/receipts', () => JSON.parse(JSON.stringify(rawReceipts as unknown as PrivacyReceipt[])));
}

export async function getArchitecture(): Promise<ArchitecturePayload> {
  return safeFetch('/api/architecture', () => ({
    title: 'ARGUS Architecture & Hybrid Zero-Egress Deployment Guide',
    runtime_mode: 'cloud_showcase',
    case_study: {
      startup_name: 'SwasthyaPay Technologies Pvt Ltd',
      industry: 'FinTech / HealthTech Infrastructure (Series A)',
      headquarters: 'Bengaluru & Mumbai, India',
      cloud_region: 'AWS ap-south-1 (Mumbai)',
      problem_statement:
        'Fast-growing Indian startup handling 4.2M citizen health records and Aadhaar KYC documents. Non-compliant with India DPDP Act 2023 Rules 6, 7, 8, and 15, facing potential statutory penalties up to ₹250 Crores ($30M). Unable to afford enterprise MSSPs or send proprietary customer data to external public AI models (OpenAI/Anthropic) due to strict Section 8 non-egress regulations.',
      before_argus: {
        active_violations: 12,
        dpdp_readiness_score: '54% (Failing)',
        attack_path_likelihood: '90.6%',
        mean_time_to_remediate: '14 business days',
        cloud_data_egress_risk: 'Severe (Secrets in plain text)',
      },
      after_argus: {
        active_violations: '0 Critical (100% compliant)',
        dpdp_readiness_score: '98% (Certified)',
        attack_path_likelihood: '31.0% (Eliminated primary paths with budget K=3)',
        mean_time_to_remediate: '< 2.5 seconds autonomous synthesis',
        cloud_data_egress_risk: '0.00 bytes leaked (HMAC-SHA256 Airlock Proof)',
      },
    },
    hybrid_topology: {
      cloud_portal: {
        name: 'AWS Free Tier Showcase Portal',
        endpoint: 'http://13.201.224.53/',
        instance: 'EC2 t3.micro (ap-south-1 Mumbai, 1 GB RAM)',
        stores_customer_secrets: false,
        capabilities: [
          'Pre-seeded SwasthyaPay Judge Sandbox',
          'Animated 6-stage demo.py Pipeline Visualizer',
          'Phase 5 + Phase 6 CrossFit OOF Empirical Results (/results)',
          'DPDP Act 2023 & Hybrid Docs (/docs)',
          'Desktop Releases & Local Bridge Probe (/downloads)',
        ],
      },
      local_engine: {
        name: 'Local Windows / Private VPC Engine',
        endpoint: 'http://127.0.0.1:8742',
        stores_customer_secrets: false,
        zero_egress: true,
        capabilities: [
          'Local Terraform (.tf) & AWS Read-Only boto3 Scanner (iam_guard checked)',
          'In-Memory Cartography Session + NetworkX Attack Graph + PuLP/SciPy MILP',
          'Fernet SQLite Privacy Airlock (vault.db) + Presidio/Secret Scrubbers',
          'Tier 0 Deterministic Templates + Local Ollama (argus-m1-sft)',
          'Bundled OPA Rego Verification Gate + Terraform .patch / Audit ZIP Export',
        ],
      },
      browser_bridge: {
        protocol: 'Direct Client-Side Loopback (CORS + Chrome Private Network Access)',
        description:
          'Viewer switches from Cloud Demo to Local Engine (127.0.0.1:8742) directly inside the browser; private cloud data never transits EC2.',
      },
    },
    pipeline_layers: [
      {
        layer: 1,
        name: 'Cloud IaC & Topology Ingestion',
        components: ['AWS Read-Only boto3 (iam_guard)', 'Terraform HCL Parser', 'In-Memory Cartography Session'],
        purpose: 'Constructs the full cloud identity, permission, and asset graph locally without requiring Docker or external uploads.',
      },
      {
        layer: 2,
        name: 'Zero-Egress Privacy Airlock',
        components: ['Fernet Encrypted TokenVault', 'Presidio & Secret Scrubbers', 'SHA-256 Leak-Check Receipts'],
        purpose: 'Projects only Rego-declared attributes and tokenizes account numbers, ARNs, and credentials before synthesis.',
      },
      {
        layer: 3,
        name: 'Risk & Interdiction Engine',
        components: ['Personalized PageRank (PPR)', 'SciPy / PuLP MILP Solver', 'Independent Dijkstra Verifier'],
        purpose: 'Selects the minimal set of security interventions (K budget) to sever attacker entry paths to Crown Jewels.',
      },
      {
        layer: 4,
        name: 'On-Device Model Synthesis (M1)',
        components: ['Tier 0 Deterministic Templates (0.4ms)', 'Ollama Local Inference (127.0.0.1:11434)', 'argus-m1-sft (Qwen3.5-4B Q4_K_M)'],
        purpose: 'Generates schema-constrained Patch-IR JSON on-device with zero outbound requests.',
      },
      {
        layer: 5,
        name: 'Automated Verification Gate',
        components: ['Open Policy Agent (opa.exe Rego)', 'Intent & No-New-Principal Checks', 'M2 LTT Decision Guardrail'],
        purpose: 'Prevents hallucination or unsafe deletions; holds autonomy OFF until conformal tau_star.json is certified.',
      },
      {
        layer: 6,
        name: 'Terraform Diff & Audit Exporter',
        components: ['Unified .patch HCL Writer', 'DPDP Compliance Scorecard', 'Auditor ZIP Evidence Bundle'],
        purpose: 'Emits clean, reviewable Terraform diffs and tamper-evident compliance receipts.',
      },
    ],
    deployment_options: [
      {
        type: 'Hybrid Mode: AWS Free Tier Portal + Local Desktop Agent (Recommended)',
        cost: '₹0 / month (AWS Free Tier + Local PC)',
        description: 'Public showcase runs on EC2 t3.micro (zero customer data) while scanning, graph solving, and Ollama M1 run strictly on 127.0.0.1:8742.',
      },
      {
        type: 'Air-Gapped In-VPC Private Subnet',
        cost: 'Standard AWS EC2 compute',
        description: 'Enterprise and regulated healthtech topology with zero outbound NAT Gateway egress for maximum DPDP Section 8 compliance.',
      },
      {
        type: 'CI/CD & CLI Runner (demo.py / local_engine)',
        cost: 'Included in standard CI minutes',
        description: 'Runs Terraform HCL scan, Airlock, M1 synthesis, and OPA Rego gate on every pull request prior to deploy.',
      },
    ],
  }));
}

export async function runLivePipeline(scenario: string = 'encryption'): Promise<PipelineExecutionResult> {
  const res = await fetch(`${getApiBase()}/api/pipeline/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario }),
  });
  if (!res.ok) {
    throw new Error(`Pipeline run failed with status ${res.status}`);
  }
  const data = await res.json();
  useWorkspaceStore.getState().bumpWorkspaceRevision();
  return data;
}

export async function resetPipeline(): Promise<void> {
  await fetch(`${getApiBase()}/api/pipeline/reset`, { method: 'POST' });
  useFindingsStore.getState().resetFindings();
  useWorkspaceStore.getState().bumpWorkspaceRevision();
}

export async function getHealth(): Promise<HealthPayload | null> {
  return safeFetch<HealthPayload | null>('/api/health', () => null);
}

export async function getReleases(): Promise<ReleasesPayload> {
  return safeFetch<ReleasesPayload>('/api/releases', () => JSON.parse(JSON.stringify(rawReleases)));
}

export async function getBenchmarks(): Promise<BenchmarksPayload> {
  return safeFetch<BenchmarksPayload>('/api/benchmarks', () => JSON.parse(JSON.stringify(rawBenchmarks)));
}

export async function getDocsSpec(): Promise<DocsPayload> {
  return safeFetch<DocsPayload>('/api/docs', () => ({
    title: 'ARGUS Enterprise & Developer Documentation',
    hybrid_layers: [
      {
        layer: '1. Public Cloud Showcase Portal',
        host: 'AWS EC2 t3.micro (ap-south-1 Mumbai, 13.201.224.53)',
        role: 'Interactive Judge Sandbox, Live 6-Stage Visualizer, Empirical Benchmarks, Documentation, and Desktop Releases Hub.',
        data_boundary: 'Zero customer secrets. Static React SPA + synthetic SwasthyaPay demo.',
      },
      {
        layer: '2. Local Windows / VPC Execution Engine',
        host: '127.0.0.1:8742 (Customer Laptop or Private Subnet)',
        role: 'Real Terraform & AWS boto3 scanners (iam_guard checked), NetworkX + MILP, Fernet Vault Airlock, Ollama argus-m1-sft, bundled opa.exe, .patch exporter.',
        data_boundary: '100% on-device loopback. Zero network egress to EC2 showcase.',
      },
      {
        layer: '3. Hybrid Browser Bridge',
        host: 'Client Browser (Chrome / Edge Private Network Access)',
        role: 'Lets CISOs on 13.201.224.53 switch directly to 127.0.0.1:8742 when local engine is running without routing private payloads through EC2.',
        data_boundary: 'Browser <-> Loopback 127.0.0.1 only.',
      },
    ],
    dpdp_rule_matrix: [
      {
        dpdp_rule: 'Rule 6(1)(a) — Encryption at Rest & Transit',
        rego_files: ['policy/dpdp/rule6a.rego', 'policy/dpdp/rule6a_rds.rego'],
        rule_ids: ['dpdp.rule6a', 'dpdp.rule6a_rds', 'cis.s3_default_encryption'],
        technical_check: 'S3 buckets and RDS instances holding personal data must enforce AES256/aws:kms encryption.',
        tier: 'T0 Template / T1 M1',
      },
      {
        dpdp_rule: 'Rule 6 — Public Access & Network Perimeter',
        rego_files: ['policy/dpdp/rule6_public.rego', 'policy/dpdp/rule6_access_sg.rego'],
        rule_ids: ['dpdp.rule6_public_exposure', 'dpdp.rule6_sg_open_ingress', 'cis.s3_public_access_block'],
        technical_check: 'Enforce all 4 S3 Public Access Block booleans; block 0.0.0.0/0 on sensitive ports (22, 3389, 3306, 5432, etc.).',
        tier: 'T0 Template / T1 M1',
      },
      {
        dpdp_rule: 'Rule 6 — Recoverability & Access MFA',
        rego_files: ['policy/dpdp/rule6_versioning.rego', 'policy/dpdp/rule6_mfa.rego'],
        rule_ids: ['dpdp.rule6_versioning', 'dpdp.rule6_account_mfa'],
        technical_check: 'Personal-data buckets require versioning Enabled; account-level MFA must be active.',
        tier: 'T0 Template / T3 Review',
      },
      {
        dpdp_rule: 'Rule 6 & Rule 7 — Logging & 72h Breach Readiness',
        rego_files: ['policy/dpdp/rule6_logging.rego', 'policy/dpdp/rule7_detection.rego'],
        rule_ids: ['dpdp.rule6_logging', 'dpdp.rule7_detection'],
        technical_check: 'S3 server access logging, CloudTrail, and GuardDuty must remain enabled for forensic traceability.',
        tier: 'T0 Template / T1 M1',
      },
      {
        dpdp_rule: 'Rule 8 — Data Minimization & Retention',
        rego_files: ['policy/dpdp/rule8_lifecycle.rego'],
        rule_ids: ['dpdp.rule8_lifecycle'],
        technical_check: 'Buckets storing personal data must configure an enabled lifecycle expiration rule.',
        tier: 'T0 Template',
      },
      {
        dpdp_rule: 'Rule 15 — Cross-Border Transfer Visibility',
        rego_files: ['policy/dpdp/rule15_region.rego'],
        rule_ids: ['dpdp.rule15_region'],
        technical_check: 'Permissive visibility flag (warn, never hard-fail) highlighting personal-data buckets outside ap-south-1.',
        tier: 'Visibility Flag',
      },
    ],
    iam_guard_forbidden_sample: [
      's3:GetObject',
      's3:GetObjectVersion',
      'secretsmanager:GetSecretValue',
      'ssm:GetParameter',
      'kms:Decrypt',
      'dynamodb:GetItem',
      'dynamodb:Query',
      'rds-data:ExecuteStatement',
      'athena:StartQueryExecution',
    ],
    patch_ir_schema: {
      required: ['finding_id', 'resource_ref', 'ops', 'rationale_ref'],
      ops_enum: [
        'set_attr',
        'add_policy_statement',
        'remove_policy_statement',
        'restrict_cidr',
        'enable_feature',
        'set_lifecycle_rule',
        'escalate',
      ],
    },
  }));
}

export async function probeLocalEngine(url = 'http://127.0.0.1:8742'): Promise<LocalStatusPayload | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2800);
  try {
    const res = await fetch(`${url.replace(/\/+$/, '')}/api/local/status`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const data = (await res.json()) as LocalStatusPayload;
    return data.can_scan_local ? data : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function getLocalStatus(): Promise<LocalStatusPayload> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/status`, { headers: { Accept: 'application/json' } });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Local status failed (${res.status})`);
  }
  return body as LocalStatusPayload;
}

export async function scanTerraformApi(directory: string, region = 'ap-south-1', orgName?: string): Promise<ScanResultPayload> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/scan/terraform`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ directory, region, orgName }),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Terraform scan failed (${res.status})`);
  }
  await getFindings().catch(() => {});
  useWorkspaceStore.getState().bumpWorkspaceRevision();
  return body as ScanResultPayload;
}

export async function scanAwsApi(payload: {
  profile?: string;
  roleArn?: string;
  externalId?: string;
  region?: string;
  orgName?: string;
}): Promise<ScanResultPayload> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/scan/aws`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `AWS scan failed (${res.status})`);
  }
  await getFindings().catch(() => {});
  useWorkspaceStore.getState().bumpWorkspaceRevision();
  return body as ScanResultPayload;
}

export async function importLocalModelApi(ggufPath: string, modelName = 'argus-m1-sft'): Promise<{ success: boolean; model_name: string; template_source?: string; stdout?: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/models/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ggufPath, modelName }),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Model import failed (${res.status})`);
  }
  return body;
}

export async function getDiscoveredModelsApi(): Promise<{
  ggufs: DiscoveredGguf[];
  ollama: LocalStatusPayload['ollama'];
  pull_status: OllamaPullStatus;
}> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/models/discovered`, { headers: { Accept: 'application/json' } });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Model discovery failed (${res.status})`);
  }
  return body;
}

export async function pullOllamaModelApi(model: string): Promise<OllamaPullStatus> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/models/pull`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Ollama pull failed (${res.status})`);
  }
  return body as OllamaPullStatus;
}

export async function getPullStatusApi(): Promise<OllamaPullStatus> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/models/pull-status`, { headers: { Accept: 'application/json' } });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Pull status failed (${res.status})`);
  }
  return body as OllamaPullStatus;
}

export async function startOllamaApi(): Promise<LocalStatusPayload['ollama']> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/ollama/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Failed to start Ollama (${res.status})`);
  }
  return body.ollama as LocalStatusPayload['ollama'];
}

export async function getAwsProfilesApi(): Promise<string[]> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/aws-profiles`, { headers: { Accept: 'application/json' } });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Failed to read AWS profiles (${res.status})`);
  }
  return Array.isArray(body?.profiles) ? body.profiles : [];
}

export async function pickLocalFolderApi(initialDir?: string): Promise<string | null> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/dialog/folder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initialDir }),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Folder dialog failed (${res.status})`);
  }
  return body?.selected || null;
}

export async function pickLocalFileApi(initialDir?: string): Promise<string | null> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/local/dialog/file`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initialDir }),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `File dialog failed (${res.status})`);
  }
  return body?.selected || null;
}

export async function scanGithubRepoApi(payload: {
  repoUrl: string;
  branch?: string;
  subpath?: string;
  region?: string;
  orgName?: string;
}): Promise<ScanResultPayload> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/scan/github`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `GitHub Terraform scan failed (${res.status})`);
  }
  await getFindings().catch(() => {});
  useWorkspaceStore.getState().bumpWorkspaceRevision();
  return body as ScanResultPayload;
}

export async function exportFindingPatchApi(findingId: string): Promise<{ success: boolean; patch_path: string; content: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/approvals/${findingId}/export-patch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.message || body?.error || `Patch export failed (${res.status})`);
  }
  return body;
}

export function getAuditExportUrl(): string {
  return `${getApiBase()}/api/audit/export`;
}

export async function connectTenantApi(payload: TenantConnectPayload): Promise<TenantInfo> {
  const raw = await safeFetch<any>(
    '/api/tenant/connect',
    () => ({
      tenantId: 'tnt_in_9021',
      orgName: payload.orgName,
      awsAccountId: payload.awsAccountId,
      region: payload.region,
      iamRoleArn: payload.iamRoleArn,
      externalId: payload.externalId,
      ollamaEndpoint: payload.ollamaEndpoint,
      status: 'ACTIVE' as const,
      nodesDiscovered: 48,
      edgesDiscovered: 112,
      rulesEvaluated: 12,
      dpdpScore: 54,
      connectedAt: new Date().toISOString(),
    }),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
  const t = raw?.tenant || raw || {};
  return {
    tenantId: t.tenantId || t.tenant_id || 'tnt_in_9021',
    orgName: t.orgName || t.org_name || payload.orgName,
    awsAccountId: t.awsAccountId || t.aws_account_id || payload.awsAccountId,
    region: t.region || payload.region,
    iamRoleArn: t.iamRoleArn || t.iam_role_arn || payload.iamRoleArn,
    externalId: t.externalId || t.external_id || payload.externalId,
    ollamaEndpoint: t.ollamaEndpoint || t.ollama_endpoint || payload.ollamaEndpoint,
    status: (t.status || 'ACTIVE') as any,
    nodesDiscovered: t.nodesDiscovered ?? t.nodes_discovered ?? 48,
    edgesDiscovered: t.edgesDiscovered ?? t.edges_discovered ?? 112,
    rulesEvaluated: t.rulesEvaluated ?? t.rules_evaluated ?? 12,
    dpdpScore: t.dpdpScore ?? t.dpdp_score ?? 54,
    connectedAt: t.connectedAt || t.connected_at || new Date().toISOString(),
  };
}

export async function getTenantStatusApi(): Promise<TenantInfo> {
  const raw = await safeFetch<any>('/api/tenant/status', () => ({
    tenantId: 'tnt_in_9021',
    orgName: 'SwasthyaPay Technologies Pvt Ltd',
    awsAccountId: '987654321098',
    region: 'ap-south-1',
    iamRoleArn: 'arn:aws:iam::987654321098:role/argus-audit-role',
    externalId: 'argus-tnt-9021-mumbai',
    ollamaEndpoint: 'http://localhost:11434',
    status: 'ACTIVE' as const,
    nodesDiscovered: 48,
    edgesDiscovered: 112,
    rulesEvaluated: 12,
    dpdpScore: 98,
    connectedAt: '2026-11-21T10:00:00Z',
  }));
  const t = raw?.tenant || raw || {};
  return {
    tenantId: t.tenantId || t.tenant_id || 'tnt_in_9021',
    orgName: t.orgName || t.org_name || 'SwasthyaPay Technologies Pvt Ltd',
    awsAccountId: t.awsAccountId || t.aws_account_id || '987654321098',
    region: t.region || 'ap-south-1',
    iamRoleArn: t.iamRoleArn || t.iam_role_arn || 'arn:aws:iam::987654321098:role/argus-audit-role',
    externalId: t.externalId || t.external_id || 'argus-tnt-9021-mumbai',
    ollamaEndpoint: t.ollamaEndpoint || t.ollama_endpoint || 'http://localhost:11434',
    status: (t.status || 'ACTIVE') as any,
    nodesDiscovered: t.nodesDiscovered ?? t.nodes_discovered ?? 48,
    edgesDiscovered: t.edgesDiscovered ?? t.edges_discovered ?? 112,
    rulesEvaluated: t.rulesEvaluated ?? t.rules_evaluated ?? 12,
    dpdpScore: t.dpdpScore ?? t.dpdp_score ?? 98,
    connectedAt: t.connectedAt || t.connected_at || '2026-11-21T10:00:00Z',
  };
}

