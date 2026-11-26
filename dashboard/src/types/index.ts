// Core Data Contracts for ARGUS Cloud Security Dashboard

export type NodeKind = 'user' | 'role' | 'key' | 'sg' | 'bucket' | 'stmt' | 'admin' | string;

export type EdgeType =
  | 'CAN_ESCALATE'
  | 'DIRECT_ADMIN'
  | 'CAN_ACCESS'
  | 'RULE_TO_SG'
  | 'USES_KEY'
  | 'CAN_ASSUME'
  | string;

export interface iamNodes {
  id: string;
  label: string;
  kind: NodeKind;
  risk: number; // 0 - 100
  isEntry?: boolean;
  isCrownJewel?: boolean;
  x?: number; // Deterministic coordinate for 2D Canvas (0 - 1000 scale)
  y?: number; // Deterministic coordinate for 2D Canvas (0 - 500 scale)
  details?: Record<string, any>;
}

export interface iamEdges {
  source: string;
  target: string;
  etype: EdgeType;
  p: number; // 0.0 - 1.0 probability
  isAttackPath?: boolean;
  isInterdicted?: boolean;
  residual?: boolean;
}

export interface GraphPayload {
  nodes: iamNodes[];
  edges: iamEdges[];
}

export type FindingStatus = 'APPROVED' | 'NEEDS_REVIEW' | 'ESCALATED' | 'APPLIED';
export type AutoApplyStatus = 'APPROVED' | 'NEEDS_APPROVAL' | 'ESCALATED' | 'APPLIED';

export interface iamFindings {
  finding_id: string;
  rule_id: string;
  rule_title?: string;
  title: string;
  resource_id: string;
  resource_type: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  status: FindingStatus;
  auto_apply_status?: AutoApplyStatus;
  confidence: number | 'n/a';
  m2_confidence?: number | null;
  threshold: number; // e.g. 0.95
  conformal_threshold?: number;
  certified: boolean;
  reason: string;
  escalated: boolean;
  tier_used: 'T0' | 'T1' | 'T2' | 'T3';
  generator_model?: 'deterministic_template' | 'argus-m1-sft' | 'human' | string;
  latency_ms?: number;
  cost?: number; // 1 (restrict_cidr) or 2 (remove_policy_statement)
  edges_covered?: string[]; // IDs or source->target strings
  patch_ir?: {
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
  diff?: {
    before: string;
    after: string;
  };
  privacy_receipt_id?: string;
  privacy_receipt?: PrivacyReceipt;
}

export interface iamComp {
  rule_id: string;
  name: string;
  compliance_pct?: number;
  score_pct?: number; // Optional for Rule 15 which has no progress bar
  failing_count?: number;
  violations_count?: number;
  review_count?: number;
  status: 'PASS' | 'WARNING' | 'FAIL' | 'FLAGGED';
  is_visibility_flag?: boolean; // Rule 15 Region is a visibility flag, never a failure
  category: string;
  description?: string;
  finding_ids?: string[];
  residency?: {
    home_region: string;
    cross_border_resources: string[];
  };
}

export interface SelectedFix {
  rank: number;
  finding_id: string;
  title: string;
  rule_id: string;
  resource_id: string;
  edge_cut: string;
  marginal_reduction: number;
}

export interface ParetoPoint {
  budget: number;
  residual: number; // Interdiction MILP
  naive_residual: number; // Naive top-K
  stackelberg_residual: number; // Stackelberg game
}

export interface iamRem {
  budget: number; // 0 - 10, default 3
  baseline_likelihood: number; // 0.906
  residual_likelihood: number; // e.g. 0.586
  selected_findings: string[]; // finding IDs e.g. ['F-b42cc0f7']
  edges_interdicted: Array<{ source: string; target: string }>;
  cost_spent: number;
  attacker_shortest_path_cost: number;
  baseline_path_cost?: number;
  selected_fixes?: SelectedFix[];
  pareto_curve: ParetoPoint[];
}

export interface PrivacyReceipt {
  receipt_id: string;
  finding_id: string;
  timestamp: string;
  rule_id: string;
  projected_fields: Record<string, any>;
  tokens: Record<string, string>;
  scrub_result: {
    presidio_hits: number;
    secret_scan_hits: number;
  };
  tier_used: string;
  leaked_to_network: boolean;
}

export interface OverviewPayload {
  scan_id: string;
  region: string;
  scanned_time: string;
  is_on_device: boolean;
  runtime_mode?: 'cloud_showcase' | 'local_agent';
  source_mode?: string;
  user_name: string;
  certified: boolean;
  greeting?: string;
  headline: string;
  subline: string;
  action_button_label: string;
  auto_apply_threshold_pct: number;
  waiting_findings: iamFindings[];
  compliance: iamComp[];
  interdiction: iamRem;
  pending_approvals_count: number;
  graph_summary: {
    total_nodes: number;
    total_edges: number;
  };
}

export interface PipelineStageResult {
  stage: number;
  name: string;
  status: string;
  latency_ms: number;
  details: string;
  patch_ir?: any;
  hcl_diff?: {
    before: string;
    after: string;
  };
}

export interface PipelineExecutionResult {
  success: boolean;
  scenario: string;
  title: string;
  rule_id: string;
  total_latency_ms: number;
  stages: PipelineStageResult[];
  patch_ir: any;
  diff: {
    before: string;
    after: string;
  };
  receipt: any;
}

export interface ArchitecturePayload {
  title: string;
  runtime_mode?: 'cloud_showcase' | 'local_agent';
  case_study: {
    startup_name: string;
    industry: string;
    headquarters: string;
    cloud_region: string;
    problem_statement: string;
    before_argus: Record<string, string | number>;
    after_argus: Record<string, string | number>;
  };
  hybrid_topology?: {
    cloud_portal: {
      name: string;
      endpoint: string;
      instance: string;
      stores_customer_secrets: boolean;
      capabilities: string[];
    };
    local_engine: {
      name: string;
      endpoint: string;
      stores_customer_secrets: boolean;
      zero_egress: boolean;
      capabilities: string[];
    };
    browser_bridge: {
      protocol: string;
      description: string;
    };
  };
  pipeline_layers: Array<{
    layer: number;
    name: string;
    components: string[];
    purpose: string;
  }>;
  deployment_options: Array<{
    type: string;
    cost: string;
    description: string;
  }>;
}

export interface HealthPayload {
  status: string;
  platform: string;
  version: string;
  runtime_mode?: 'cloud_showcase' | 'local_agent';
  can_scan_local?: boolean;
  can_run_local_llm?: boolean;
  cloud_host: string;
  hackathon: string;
  compliance_engines: string[];
  zero_data_egress_enforced: boolean;
  m1_primary_model?: string;
  m2_certified?: boolean;
  autonomy_status?: string;
  active_models: string[];
  verification_gate: string;
  ollama_available: boolean;
  airlock_available: boolean;
  gate_available: boolean;
  local_engine_available?: boolean;
}

export interface DiscoveredGguf {
  name: string;
  path: string;
  size_bytes: number;
  size_gb: number;
  suggested_model_name: string;
}

export interface OllamaPullStatus {
  active: boolean;
  model: string | null;
  status: string;
  completed_bytes: number;
  total_bytes: number;
  percent: number;
  success: boolean | null;
  error: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  already_running?: boolean;
}

export interface LocalStatusPayload {
  runtime_mode: 'cloud_showcase' | 'local_agent';
  can_scan_local: boolean;
  opa_ready: boolean;
  opa_path?: string | null;
  airlock_ready?: boolean;
  t0_ready?: boolean;
  gate_ready?: boolean;
  ollama: {
    running: boolean;
    endpoint?: string;
    version?: string | null;
    models: string[];
    argus_sft_ready: boolean;
    argus_rft_ready: boolean;
    ollama_installed?: boolean;
    error?: string | null;
  };
  discovered_ggufs?: DiscoveredGguf[];
  pull_status?: OllamaPullStatus;
  aws_profiles?: string[];
  m2_status: {
    certified: boolean;
    tau?: number | null;
    status: string;
    message: string;
  };
  exports_dir?: string;
  sample_terraform_dir?: string;
  source_mode?: string;
  recent_scans?: Array<{
    scan_id: string;
    scanned_at: string;
    source_type: string;
    target: string;
    findings_count: number;
    nodes_count: number;
    edges_count: number;
  }>;
}

export interface ReleasesPayload {
  product: string;
  latest_version: string;
  repo_url: string;
  live_portal_url: string;
  distribution_strategy: string;
  desktop_build_status: string;
  runtime_mode?: string;
  desktop_architecture_choices?: Record<string, string>;
  current_release: {
    version: string;
    codename?: string;
    released_at?: string;
    portal_status?: string;
    artifacts: Array<{
      id: string;
      name: string;
      platform: string;
      packaging: string;
      estimated_size: string;
      size_display?: string;
      size_bytes?: number;
      status: string;
      download_ready: boolean;
      download_url: string | null;
      portal_download_url?: string | null;
      github_release_url?: string | null;
      sha256: string;
      notes: string;
    }>;
    model_packs: Array<{
      id: string;
      name: string;
      base_model: string;
      size: string;
      status: string;
      download_ready: boolean;
      download_url: string | null;
      ollama_pull_ref?: string | null;
      ollama_digest?: string;
      register_cmd: string;
      pass_at_1_oof?: string;
      pass_at_1_c_verifier?: string;
      notes: string;
    }>;
  };
  versions: Array<{
    version: string;
    date: string;
    title: string;
    tag: string;
    status: string;
    highlights: string[];
  }>;
}

export interface BenchmarksPayload {
  runtime_mode?: string;
  generated_from?: string[];
  headline_metrics: {
    oof_pass_at_1_pct: number;
    oof_passed_examples: number;
    oof_total_examples: number;
    oof_distinct_keys_passed: number;
    oof_distinct_keys_total: number;
    oof_schema_valid_pct: number;
    clean_unseen_clusters: number;
    stop_rule_s4_min_clusters: number;
    cluster_margin: number;
    rft_unsafe_candidates: number;
    rft_total_candidates: number;
    adversarial_defense_passed: number;
    adversarial_defense_total: number;
    milp_beats_naive_49_of_50: string;
    primary_m1_model: string;
  };
  phase6_crossfit_oof: {
    commit: string;
    base_model: string;
    k_folds_total: number;
    folds_evaluated: number;
    overall_pass_at_1: number;
    overall_ci_low: number;
    overall_ci_high: number;
    total_passed_examples: number;
    total_examples: number;
    total_distinct_passed: number;
    total_distinct_inputs: number;
    distinct_key_pass_pct: number;
    schema_valid_pct: number;
    oof_clean_clusters: number;
    existing_prod_clusters: number;
    total_clean_clusters: number;
    folds: Array<{
      fold: string;
      held_out_inputs: number;
      clean_clusters: number;
      pass_at_1_pct: number;
      passed: number;
      total: number;
      ci_low: number;
      ci_high: number;
      distinct_passed: number;
      distinct_total: number;
      schema_valid_pct: number;
      checkpoint: string;
    }>;
    stop_rule_s4: Array<{
      metric: string;
      required: number;
      delivered: number;
      margin: string;
    }>;
  };
  phase5_benchmarks: {
    tag: string;
    synthetic_examples: number;
    train_examples: number;
    val_examples: number;
    heldout_examples: number;
    real_github_repos_scanned: number;
    tier0_coverage_val_pct: number;
    tier0_coverage_real_pct: number;
    tier0_latency_ms: number;
    splits: Array<{
      split: string;
      zeroshot_pass1: number;
      sft_pass1: number;
      rft_pass1: number;
      zeroshot_ci: [number, number];
      sft_ci: [number, number];
      rft_ci: [number, number];
    }>;
    safety_audit: Array<{
      model: string;
      unsafe_count: number;
      total_candidates: number;
      unsafe_rate_pct: number;
      schema_valid_pct: number;
      hidden_check_pass_pct: number;
      median_latency_s: string;
    }>;
    adversarial_probes: {
      gate_payloads_tested: number;
      gate_payloads_rejected: number;
      injection_findings_tested: number;
      injection_unsafe_accepted: number;
    };
  };
  phase6_audit_and_parity: {
    harvest_total_rows: number;
    harvest_inputs: number;
    harvest_samples_per_input: number;
    harvest_verdict: string;
    model_selection_rule_5_2: string;
    harvest_generators?: Array<{
      generator: string;
      rows: number;
      aligned_a_val_pass1_pct: number;
      a_val_counts: string;
      schema_valid_pct: number;
      verdict: string;
    }>;
    counterfactual_oracle_agreed: number;
    counterfactual_oracle_total: number;
    counterfactual_oracle_rate_pct: number;
    feature_parity_checked: number;
    feature_parity_mismatches: number;
  };
  interdiction_milp: {
    n_seeds: number;
    mean_solve_time_ms: number;
    max_solve_time_ms: number;
    brute_force_mismatches: number;
    scale_probe_findings: number;
    scale_probe_pulp_ms: number;
    scale_probe_scipy_ms: number;
    budgets: Array<{
      budget: number;
      better_than_naive: number;
      better_than_stackelberg: number;
      tied: number;
      n_instances: number;
      mean_milp_residual: number;
      mean_naive_residual: number;
      mean_stackelberg_residual: number;
    }>;
  };
  m2_ltt_governance: {
    certified: boolean;
    status: string;
    autonomy_mode: string;
    alpha: number;
    delta: number;
    c_FA: number;
    c_esc: number;
    bayes_cutoff: number;
    tau_star: number | null;
    n_min_clusters: number;
    n_pre_oof_clusters: number;
    n_post_oof_available: number;
    message: string;
    monte_carlo_reps_per_regime: number;
    monte_carlo_regimes: Array<{
      regime: string;
      n_cal: number;
      true_err: number;
      certified_frac: number;
      ltt_coverage: number | null;
      crc_coverage: number;
      crc_exceeds_alpha: boolean;
      max_cond_error: number;
    }>;
  };
  test_suites: Array<{
    suite: string;
    count?: number;
    status: string;
    notes: string;
  }>;
}

export interface DocsPayload {
  title: string;
  runtime_mode?: string;
  hybrid_layers: Array<{
    layer: string;
    host: string;
    role: string;
    data_boundary: string;
  }>;
  dpdp_rule_matrix: Array<{
    dpdp_rule: string;
    rego_files: string[];
    rule_ids: string[];
    technical_check: string;
    tier: string;
  }>;
  iam_guard_forbidden_sample: string[];
  patch_ir_schema: any;
}

export interface ScanResultPayload {
  success: boolean;
  scan_id: string;
  source_type: 'terraform' | 'aws';
  target?: string;
  repo_url?: string;
  branch?: string | null;
  subpath?: string | null;
  commit?: string;
  account_id?: string;
  identity?: string;
  files_scanned?: string[];
  watchlist_warnings?: string[];
  opa_used: boolean;
  findings_count: number;
  nodes_count: number;
  edges_count: number;
  m2_status?: any;
}

export interface TenantInfo {
  tenantId: string;
  orgName: string;
  awsAccountId: string;
  region: string;
  iamRoleArn: string;
  externalId: string;
  ollamaEndpoint?: string;
  status: 'ACTIVE' | 'CONNECTING' | 'PENDING';
  nodesDiscovered?: number;
  edgesDiscovered?: number;
  rulesEvaluated?: number;
  dpdpScore?: number;
  connectedAt?: string;
}

export interface TenantConnectPayload {
  orgName: string;
  awsAccountId: string;
  region: string;
  iamRoleArn: string;
  externalId: string;
  ollamaEndpoint: string;
  dpdpScope: string[];
}


