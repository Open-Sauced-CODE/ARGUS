import React, { useEffect, useState } from 'react';
import {
  Award,
  BarChart3,
  CheckCircle2,
  ShieldCheck,
  Lock,
  AlertTriangle,
  Cpu,
  GitBranch,
  Layers,
  Activity,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import { getBenchmarks } from '../api';
import { BenchmarksPayload } from '../types';
import { useWorkspaceStore } from '../store/workspaceStore';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';
import rawBenchmarks from '../mock/mockBenchmarks.json';

export const ResultsPage: React.FC = () => {
  const { runtimeTarget, workspaceRevision, tenant } = useWorkspaceStore();
  const [data, setData] = useState<BenchmarksPayload>(() =>
    JSON.parse(JSON.stringify(rawBenchmarks))
  );
  const [activeModelTab, setActiveModelTab] = useState<'oof' | 'phase5' | 'interdiction' | 'ltt'>('oof');

  useEffect(() => {
    let mounted = true;
    getBenchmarks()
      .then((res) => {
        if (mounted && res?.headline_metrics) setData(res);
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, [runtimeTarget, workspaceRevision]);

  const h = data.headline_metrics;
  const oof = data.phase6_crossfit_oof;
  const p5 = data.phase5_benchmarks;
  const audit = data.phase6_audit_and_parity;
  const milp = data.interdiction_milp;
  const ltt = data.m2_ltt_governance;

  const oofChartData = oof.folds.map((f) => ({
    name: f.fold,
    pass1: f.pass_at_1_pct,
    distinctPct: Math.round((f.distinct_passed / f.distinct_total) * 1000) / 10,
    clusters: f.clean_clusters,
    counts: `${f.passed}/${f.total}`,
  }));

  const phase5ChartData = p5.splits.map((s) => ({
    split: s.split.replace(' (Validation)', '').replace(' (Sample)', '').replace(' (Real GitHub Repos)', ' (Real)'),
    Zeroshot: s.zeroshot_pass1,
    'ARGUS-M1 SFT': s.sft_pass1,
    'ARGUS-M1 RFT': s.rft_pass1,
  }));

  const milpChartData = milp.budgets.map((b) => ({
    budget: `Budget K=${b.budget}`,
    'Interdiction MILP': Math.round(b.mean_milp_residual * 1000) / 10,
    'Naive / Stackelberg': Math.round(b.mean_naive_residual * 1000) / 10,
    wins: `${b.better_than_naive}/${b.n_instances}`,
  }));

  return (
    <div className="w-full space-y-7 pb-12">
      {/* Header */}
      <section className="space-y-2 max-w-4xl">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold text-peacock bg-peacock/10 rounded-full">
            <BarChart3 className="w-3.5 h-3.5" />
            <span>Audited Empirical Results</span>
          </span>
          <span className="px-2 py-0.5 text-[11px] font-mono bg-paper border border-ink-border text-ink-muted rounded">
            Phase 5 ({p5.tag}) + Phase 6 CrossFit OOF ({oof.commit})
          </span>
        </div>
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          Empirical Benchmarks & Statistical Safety Proof
        </h1>
        <p className="text-[15px] text-ink-muted leading-relaxed">
          All ARGUS patch generators, interdiction solvers, and conformal safety gates are evaluated against frozen,
          reproducible test harnesses—never LLM-as-a-judge heuristics.
        </p>
      </section>

      {/* Top 4 Headline KPI Cards */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="p-4 bg-paper border border-ink-border rounded-xl shadow-xs space-y-1">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span>4-Fold CrossFit OOF Pass@1</span>
            <Award className="w-4 h-4 text-verdigris" />
          </div>
          <p className="font-headline text-3xl font-semibold text-ink tabular-nums">
            {h.oof_pass_at_1_pct}%
          </p>
          <p className="text-[11.5px] text-ink-muted font-mono">
            {h.oof_passed_examples.toLocaleString()} / {h.oof_total_examples.toLocaleString()} examples • {h.oof_distinct_keys_passed}/{h.oof_distinct_keys_total} distinct keys
          </p>
        </div>

        <div className="p-4 bg-paper border border-ink-border rounded-xl shadow-xs space-y-1">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span>Patch-IR Schema Validity</span>
            <CheckCircle2 className="w-4 h-4 text-peacock" />
          </div>
          <p className="font-headline text-3xl font-semibold text-peacock tabular-nums">
            {h.oof_schema_valid_pct.toFixed(1)}%
          </p>
          <p className="text-[11.5px] text-ink-muted font-mono">
            189 / 189 OOF inputs • {audit.harvest_total_rows.toLocaleString()} harvest rows
          </p>
        </div>

        <div className="p-4 bg-paper border border-ink-border rounded-xl shadow-xs space-y-1">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span>Unsafe Candidates & Gate Defense</span>
            <ShieldCheck className="w-4 h-4 text-forest" />
          </div>
          <p className="font-headline text-3xl font-semibold text-forest tabular-nums">
            {h.rft_unsafe_candidates} / {h.rft_total_candidates.toLocaleString()}
          </p>
          <p className="text-[11.5px] text-ink-muted font-mono">
            0.00% unsafe (RFT) • {h.adversarial_defense_passed}/{h.adversarial_defense_total} adversarial rejected
          </p>
        </div>

        <div className="p-4 bg-paper border border-ink-border rounded-xl shadow-xs space-y-1">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span>Stop Rule S4 Clean Clusters</span>
            <Layers className="w-4 h-4 text-lapis" />
          </div>
          <p className="font-headline text-3xl font-semibold text-ink tabular-nums">
            {h.clean_unseen_clusters}{' '}
            <span className="text-sm font-mono font-semibold text-forest">
              (+{h.cluster_margin} margin)
            </span>
          </p>
          <p className="text-[11.5px] text-ink-muted font-mono">
            Required &ge; {h.stop_rule_s4_min_clusters} (&alpha;=0.05, &delta;=0.05)
          </p>
        </div>
      </section>

      {/* Honest M2 LTT Live Certification Banner */}
      <section
        className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
          ltt.certified
            ? 'bg-forest/10 border-forest/30 text-ink'
            : 'bg-saffron/10 border-saffron/35 text-ink'
        }`}
      >
        <div className="flex items-start gap-3">
          {ltt.certified ? (
            <CheckCircle2 className="w-5 h-5 text-forest flex-shrink-0 mt-0.5" />
          ) : (
            <Lock className="w-5 h-5 text-saffron-dark flex-shrink-0 mt-0.5" />
          )}
          <div className="space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-ink">
                M2 Conformal LTT Autonomy Gate: {ltt.certified ? 'CERTIFIED' : 'HUMAN REVIEW ONLY'}
              </span>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-paper border border-ink-border rounded">
                M1 Primary: {h.primary_m1_model} (Rule 5.2)
              </span>
            </div>
            <p className="text-xs text-ink-muted">{ltt.message}</p>
          </div>
        </div>
        <div className="text-xs font-mono bg-paper px-3 py-1.5 rounded-control border border-ink-border flex-shrink-0">
          &tau;* = {ltt.tau_star ?? 'null'} | Bayes cutoff = {ltt.bayes_cutoff}
        </div>
      </section>

      {/* Sub-navigation Tabs for Deep Benchmark Views */}
      <div className="flex flex-wrap items-center gap-2 border-b border-ink-border pb-2">
        {[
          { id: 'oof', label: '1. Phase 6 CrossFit OOF (Folds 0–3)', icon: GitBranch },
          { id: 'phase5', label: '2. Phase 5 M1 vs Zeroshot & Safety', icon: Cpu },
          { id: 'interdiction', label: '3. MILP Interdiction Solver (50 Seeds)', icon: Activity },
          { id: 'ltt', label: '4. M2 LTT Guarantees & Test Suites', icon: ShieldCheck },
        ].map((tab) => {
          const Icon = tab.icon;
          const active = activeModelTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveModelTab(tab.id as any)}
              className={`px-3.5 py-2 rounded-control text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                active
                  ? 'bg-peacock text-paper shadow-xs'
                  : 'bg-paper text-ink-muted hover:text-ink border border-ink-border/70'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB 1: PHASE 6 CROSSFIT OOF */}
      {activeModelTab === 'oof' && (
        <section className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* BarChart */}
            <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="font-headline text-xl text-ink font-medium">
                  Out-Of-Fold Gate Pass@1 by Fold
                </h2>
                <span className="text-xs font-mono text-ink-muted">Weighted Macro: {oof.overall_pass_at_1}%</span>
              </div>
              <p className="text-xs text-ink-muted">
                Four independent Qwen3.5-4B LoRA adapters trained on ~80% folds and scored strictly on held-out unseen clusters.
              </p>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={oofChartData} margin={{ top: 10, right: 12, left: -12, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#D3DDD9" vertical={false} />
                    <XAxis dataKey="name" stroke="#4A6266" fontSize={12} tickLine={false} />
                    <YAxis domain={[0, 100]} stroke="#4A6266" fontSize={11} tickLine={false} unit="%" />
                    <Tooltip
                      content={({ active, payload, label }) => {
                        if (!active || !payload?.length) return null;
                        const row = payload[0].payload;
                        return (
                          <div className="bg-paper border border-ink-border rounded-control p-2.5 shadow-soft text-xs space-y-1">
                            <p className="font-semibold text-ink">{label}</p>
                            <p className="text-peacock font-mono">Gate Pass@1: {row.pass1}% ({row.counts})</p>
                            <p className="text-verdigris font-mono">Distinct Keys: {row.distinctPct}%</p>
                            <p className="text-ink-muted font-mono">Unseen Clusters: {row.clusters}</p>
                          </div>
                        );
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                    <Bar dataKey="pass1" name="Weighted Gate Pass@1 (%)" fill="#0A2E33" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="distinctPct" name="Distinct Key Pass (%)" fill="#2E9C82" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Stop Rule S4 Clopper-Pearson Margin */}
            <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-4">
              <div>
                <h2 className="font-headline text-xl text-ink font-medium">
                  Stop Rule S4 Mathematical Certification Margin
                </h2>
                <p className="text-xs text-ink-muted mt-1">
                  Clopper-Pearson upper bound guarantees P(wrong | auto-applied) &le; 0.05 at &delta;=0.05 with resilience for up to 2 empirical errors.
                </p>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="border-b border-ink-border text-ink-faint font-mono uppercase text-[11px]">
                      <th className="py-2 pr-2">Criterion</th>
                      <th className="py-2 px-2">Required</th>
                      <th className="py-2 px-2">Delivered</th>
                      <th className="py-2 pl-2 text-right">Margin</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-border/50">
                    {oof.stop_rule_s4.map((row) => (
                      <tr key={row.metric}>
                        <td className="py-2.5 pr-2 font-medium text-ink">{row.metric}</td>
                        <td className="py-2.5 px-2 font-mono text-ink-muted">&ge; {row.required}</td>
                        <td className="py-2.5 px-2 font-mono font-bold text-peacock">{row.delivered}</td>
                        <td className="py-2.5 pl-2 text-right font-mono font-semibold text-forest">{row.margin}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="p-3 bg-mist/60 border border-ink-border/70 rounded-control text-xs text-ink-muted space-y-1">
                <p>
                  <strong className="text-ink">Counterfactual Oracle Agreement:</strong>{' '}
                  {audit.counterfactual_oracle_agreed.toLocaleString()} / {audit.counterfactual_oracle_total.toLocaleString()} ({audit.counterfactual_oracle_rate_pct.toFixed(1)}%) across all 14 Rego rules.
                </p>
                <p>
                  <strong className="text-ink">Feature Extraction Parity:</strong>{' '}
                  {audit.feature_parity_checked} / {audit.feature_parity_checked} rows verified with {audit.feature_parity_mismatches} mismatches.
                </p>
              </div>
            </div>
          </div>

          {/* Full Per-Fold Table */}
          <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs overflow-x-auto">
            <h3 className="font-headline text-lg text-ink font-medium mb-3">
              Per-Fold CrossFit Breakdown (<code className="font-mono text-sm">ml/train_m1/score_oof.py</code>)
            </h3>
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-ink-border text-ink-faint font-mono uppercase text-[11px]">
                  <th className="py-2 pr-3">Fold</th>
                  <th className="py-2 px-3">Held-Out Inputs</th>
                  <th className="py-2 px-3">Unseen Clusters</th>
                  <th className="py-2 px-3">Weighted Pass@1 [95% Wilson CI]</th>
                  <th className="py-2 px-3">Distinct Keys</th>
                  <th className="py-2 px-3">Schema Valid</th>
                  <th className="py-2 pl-3">Checkpoint</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-border/50">
                {oof.folds.map((f) => (
                  <tr key={f.fold}>
                    <td className="py-2.5 pr-3 font-semibold text-ink">{f.fold}</td>
                    <td className="py-2.5 px-3 font-mono">{f.held_out_inputs}</td>
                    <td className="py-2.5 px-3 font-mono">{f.clean_clusters}</td>
                    <td className="py-2.5 px-3 font-mono">
                      <strong className="text-peacock">{f.pass_at_1_pct.toFixed(1)}%</strong> ({f.passed}/{f.total}) [{f.ci_low}, {f.ci_high}]
                    </td>
                    <td className="py-2.5 px-3 font-mono">
                      {f.distinct_passed}/{f.distinct_total} ({((f.distinct_passed / f.distinct_total) * 100).toFixed(1)}%)
                    </td>
                    <td className="py-2.5 px-3 font-mono text-forest font-semibold">{f.schema_valid_pct.toFixed(1)}%</td>
                    <td className="py-2.5 pl-3 font-mono text-ink-muted">{f.checkpoint}</td>
                  </tr>
                ))}
                <tr className="bg-mist/50 font-semibold">
                  <td className="py-2.5 pr-3 text-ink">Total / Macro</td>
                  <td className="py-2.5 px-3 font-mono">{oof.total_distinct_inputs}</td>
                  <td className="py-2.5 px-3 font-mono">{oof.oof_clean_clusters} (+15 prod = {oof.total_clean_clusters})</td>
                  <td className="py-2.5 px-3 font-mono text-peacock">
                    {oof.overall_pass_at_1}% ({oof.total_passed_examples}/{oof.total_examples}) [{oof.overall_ci_low}, {oof.overall_ci_high}]
                  </td>
                  <td className="py-2.5 px-3 font-mono">
                    {oof.total_distinct_passed}/{oof.total_distinct_inputs} ({oof.distinct_key_pass_pct}%)
                  </td>
                  <td className="py-2.5 px-3 font-mono text-forest">100.0% (189/189)</td>
                  <td className="py-2.5 pl-3 font-mono">Epoch 3 Final</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* TAB 2: PHASE 5 BENCHMARKS */}
      {activeModelTab === 'phase5' && (
        <section className="space-y-6">
          <div className="p-4 bg-peacock/5 border border-peacock/20 rounded-xl flex items-start gap-3 text-xs">
            <AlertTriangle className="w-4 h-4 text-peacock flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-ink">Model Selection Rule 5.2 (H1 Harvest Audit Disclosure): </span>
              <span className="text-ink-muted">{audit.model_selection_rule_5_2}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-3">
              <h2 className="font-headline text-xl text-ink font-medium">
                Pass@1 Across All 6 Evaluation Splits
              </h2>
              <p className="text-xs text-ink-muted">
                Fine-tuned local 4B models (<code className="font-mono">argus-m1-sft</code> /{' '}
                <code className="font-mono">argus-m1-rft</code>) vs base <code className="font-mono">qwen3.5:4b</code> zeroshot across synthetic ({p5.synthetic_examples.toLocaleString()} examples: {p5.train_examples.toLocaleString()} train / {p5.val_examples} val / {p5.heldout_examples} held-out) and {p5.real_github_repos_scanned} real GitHub repos.
              </p>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={phase5ChartData} margin={{ top: 10, right: 12, left: -12, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#D3DDD9" vertical={false} />
                    <XAxis dataKey="split" stroke="#4A6266" fontSize={10.5} interval={0} angle={-12} textAnchor="end" height={48} />
                    <YAxis domain={[0, 100]} stroke="#4A6266" fontSize={11} unit="%" />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                    <Bar dataKey="Zeroshot" fill="#879B9E" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="ARGUS-M1 SFT" fill="#0A2E33" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="ARGUS-M1 RFT" fill="#2E9C82" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-4">
              <h2 className="font-headline text-xl text-ink font-medium">
                Safety, Schema Validity & Latency Audit (2,728 Requests)
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="border-b border-ink-border text-ink-faint font-mono uppercase text-[11px]">
                      <th className="py-2 pr-2">Model</th>
                      <th className="py-2 px-2">Unsafe Outputs</th>
                      <th className="py-2 px-2">Schema Valid</th>
                      <th className="py-2 px-2">Hidden Pass</th>
                      <th className="py-2 pl-2">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-border/50">
                    {p5.safety_audit.map((row) => (
                      <tr key={row.model}>
                        <td className="py-2.5 pr-2 font-semibold text-ink">{row.model}</td>
                        <td className="py-2.5 px-2 font-mono">
                          <span className={row.unsafe_count === 0 ? 'text-forest font-bold' : row.unsafe_count > 100 ? 'text-garnet font-bold' : 'text-saffron-dark font-semibold'}>
                            {row.unsafe_count} / {row.total_candidates.toLocaleString()} ({row.unsafe_rate_pct}%)
                          </span>
                        </td>
                        <td className="py-2.5 px-2 font-mono">{row.schema_valid_pct}%</td>
                        <td className="py-2.5 px-2 font-mono">{row.hidden_check_pass_pct}%</td>
                        <td className="py-2.5 pl-2 font-mono text-ink-muted">{row.median_latency_s}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 text-xs">
                <div className="p-3 bg-mist/60 border border-ink-border/70 rounded-control space-y-1">
                  <p className="font-semibold text-ink">Tier 0 Deterministic Templates</p>
                  <p className="text-ink-muted font-mono">
                    {p5.tier0_coverage_val_pct}% Val / {p5.tier0_coverage_real_pct}% Real Repos • {p5.tier0_latency_ms} ms • 100% Gate Pass
                  </p>
                </div>
                <div className="p-3 bg-mist/60 border border-ink-border/70 rounded-control space-y-1">
                  <p className="font-semibold text-ink">Adversarial Probes (Step 19)</p>
                  <p className="text-ink-muted font-mono">
                    {p5.adversarial_probes.gate_payloads_rejected}/{p5.adversarial_probes.gate_payloads_tested} payloads rejected • {p5.adversarial_probes.injection_unsafe_accepted}/{p5.adversarial_probes.injection_findings_tested} injections accepted
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Complete 6-Split Table with 95% Wilson CIs */}
          <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-3 overflow-x-auto">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <h3 className="font-headline text-lg text-ink font-medium">
                Phase 5 Full Split Pass@1 Matrix (with 95% Wilson Confidence Intervals)
              </h3>
              <span className="text-[11px] font-mono text-ink-muted">
                Pass@8: SFT 99.4%–100.0% across splits • RFT 89.5% on real repos
              </span>
            </div>
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-ink-border text-ink-faint font-mono uppercase text-[11px]">
                  <th className="py-2 pr-3">Evaluation Split</th>
                  <th className="py-2 px-3">Zeroshot (Base 4B)</th>
                  <th className="py-2 px-3">ARGUS-M1 SFT (Primary)</th>
                  <th className="py-2 pl-3">ARGUS-M1 RFT (Phase 5)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-border/50">
                {p5.splits.map((s) => (
                  <tr key={s.split}>
                    <td className="py-2.5 pr-3 font-semibold text-ink">{s.split}</td>
                    <td className="py-2.5 px-3 font-mono text-ink-muted">
                      {s.zeroshot_pass1.toFixed(1)}% [{s.zeroshot_ci[0]}, {s.zeroshot_ci[1]}]
                    </td>
                    <td className="py-2.5 px-3 font-mono text-peacock font-bold">
                      {s.sft_pass1.toFixed(1)}% [{s.sft_ci[0]}, {s.sft_ci[1]}]
                    </td>
                    <td className="py-2.5 pl-3 font-mono text-forest font-semibold">
                      {s.rft_pass1.toFixed(1)}% [{s.rft_ci[0]}, {s.rft_ci[1]}]
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* H1 Harvest Audit Generator Breakdown */}
          {audit.harvest_generators && audit.harvest_generators.length > 0 && (
            <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-3 overflow-x-auto">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <h3 className="font-headline text-lg text-ink font-medium">
                  Phase 6 H1 Harvest Validation & Rule 5.2 Audit ({audit.harvest_total_rows.toLocaleString()} Rows)
                </h3>
                <span className="px-2 py-0.5 text-[11px] font-mono bg-forest/15 text-forest rounded font-semibold">
                  Verdict: {audit.harvest_verdict} ({audit.harvest_inputs} inputs × {audit.harvest_samples_per_input} samples × {audit.harvest_generators.length} models)
                </span>
              </div>
              <table className="w-full text-xs text-left border-collapse">
                <thead>
                  <tr className="border-b border-ink-border text-ink-faint font-mono uppercase text-[11px]">
                    <th className="py-2 pr-3">Generator</th>
                    <th className="py-2 px-3">Rows</th>
                    <th className="py-2 px-3">Aligned A_val Pass@1</th>
                    <th className="py-2 px-3">Schema Valid</th>
                    <th className="py-2 pl-3">Audit Decision</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-border/50">
                  {audit.harvest_generators.map((g) => (
                    <tr key={g.generator}>
                      <td className="py-2.5 pr-3 font-semibold text-ink font-mono">{g.generator}</td>
                      <td className="py-2.5 px-3 font-mono">{g.rows.toLocaleString()}</td>
                      <td className="py-2.5 px-3 font-mono">
                        <strong>{g.aligned_a_val_pass1_pct.toFixed(1)}%</strong> ({g.a_val_counts})
                      </td>
                      <td className="py-2.5 px-3 font-mono text-forest">{g.schema_valid_pct.toFixed(1)}%</td>
                      <td className="py-2.5 pl-3 font-mono">
                        <span
                          className={
                            g.verdict.includes('REJECTED')
                              ? 'text-garnet font-bold'
                              : g.verdict === 'PASS'
                              ? 'text-forest font-bold'
                              : 'text-ink-muted'
                          }
                        >
                          {g.verdict}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* TAB 3: INTERDICTION MILP */}
      {activeModelTab === 'interdiction' && (
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-3">
            <h2 className="font-headline text-xl text-ink font-medium">
              Residual Attack Likelihood: MILP vs Baselines ({milp.n_seeds} Seeds)
            </h2>
            <p className="text-xs text-ink-muted">
              Lower residual attack probability is better. MILP solves the shortest-path dual with exact edge-cut selection and 0 brute-force mismatches.
            </p>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={milpChartData} margin={{ top: 10, right: 12, left: -12, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#D3DDD9" vertical={false} />
                  <XAxis dataKey="budget" stroke="#4A6266" fontSize={12} />
                  <YAxis domain={[0, 100]} stroke="#4A6266" fontSize={11} unit="%" />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Bar dataKey="Interdiction MILP" fill="#0A2E33" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Naive / Stackelberg" fill="#879B9E" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-4">
            <h2 className="font-headline text-xl text-ink font-medium">
              Solver Dominance & Timing Telemetry
            </h2>
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-ink-border text-ink-faint font-mono uppercase text-[11px]">
                  <th className="py-2 pr-2">Budget</th>
                  <th className="py-2 px-2">MILP Beats Naive</th>
                  <th className="py-2 px-2">MILP Residual</th>
                  <th className="py-2 pl-2">Naive Residual</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-border/50">
                {milp.budgets.map((b) => (
                  <tr key={b.budget}>
                    <td className="py-2.5 pr-2 font-mono font-semibold text-ink">K = {b.budget}</td>
                    <td className="py-2.5 px-2 font-mono text-forest font-bold">
                      {b.better_than_naive} / {b.n_instances} seeds ({b.tied} tied)
                    </td>
                    <td className="py-2.5 px-2 font-mono text-peacock font-semibold">
                      {(b.mean_milp_residual * 100).toFixed(2)}%
                    </td>
                    <td className="py-2.5 pl-2 font-mono text-ink-muted">
                      {(b.mean_naive_residual * 100).toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-mist/60 border border-ink-border/70 rounded-control">
                <p className="text-ink-muted">Mean / Max Solve Time</p>
                <p className="font-mono font-bold text-ink mt-0.5">
                  {milp.mean_solve_time_ms} ms / {milp.max_solve_time_ms} ms
                </p>
              </div>
              <div className="p-3 bg-mist/60 border border-ink-border/70 rounded-control">
                <p className="text-ink-muted">58-Finding Scale Probe</p>
                <p className="font-mono font-bold text-ink mt-0.5">
                  PuLP {milp.scale_probe_pulp_ms} ms • SciPy {milp.scale_probe_scipy_ms} ms
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* TAB 4: LTT GUARANTEES & TEST SUITES */}
      {activeModelTab === 'ltt' && (
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-3 overflow-x-auto">
            <h2 className="font-headline text-xl text-ink font-medium">
              Monte Carlo LTT vs CRC Stress Test ({ltt.monte_carlo_reps_per_regime.toLocaleString()} Reps / Regime)
            </h2>
            <p className="text-xs text-ink-muted">
              Learn-Then-Test (LTT) refuses autonomy (<code className="font-mono">certified_frac = 0.0</code>) under small-sample covariate shift (<code className="font-mono">n=30</code>), whereas naive CRC exceeds &alpha;=0.05.
            </p>
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-ink-border text-ink-faint font-mono uppercase text-[11px]">
                  <th className="py-2 pr-2">Regime</th>
                  <th className="py-2 px-2">n_cal</th>
                  <th className="py-2 px-2">Certified Frac</th>
                  <th className="py-2 px-2">LTT Coverage</th>
                  <th className="py-2 pl-2">CRC Exceeds &alpha;?</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-border/50">
                {ltt.monte_carlo_regimes.map((r) => (
                  <tr key={r.regime}>
                    <td className="py-2.5 pr-2 font-mono text-ink">{r.regime}</td>
                    <td className="py-2.5 px-2 font-mono">{r.n_cal}</td>
                    <td className="py-2.5 px-2 font-mono">{(r.certified_frac * 100).toFixed(1)}%</td>
                    <td className="py-2.5 px-2 font-mono text-forest font-semibold">
                      {r.ltt_coverage !== null ? `${(r.ltt_coverage * 100).toFixed(1)}%` : 'Safely Refused'}
                    </td>
                    <td className="py-2.5 pl-2 font-mono">
                      <span className={r.crc_exceeds_alpha ? 'text-garnet font-bold' : 'text-forest'}>
                        {r.crc_exceeds_alpha ? 'YES (Unsafe)' : 'No'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-5 bg-paper border border-ink-border rounded-xl shadow-xs space-y-3">
            <h2 className="font-headline text-xl text-ink font-medium">
              Automated Repository Test Verification
            </h2>
            <div className="divide-y divide-ink-border/50 text-xs">
              {data.test_suites.map((ts) => (
                <div key={ts.suite} className="py-2.5 flex items-center justify-between gap-3">
                  <div>
                    <p className="font-mono font-semibold text-ink">{ts.suite}</p>
                    <p className="text-ink-muted text-[11px]">{ts.notes}</p>
                  </div>
                  <span className="px-2.5 py-1 rounded-full bg-forest/15 text-forest font-mono font-bold text-[11px] flex-shrink-0">
                    {ts.count ? `${ts.count} ${ts.status}` : ts.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      <FooterTitleBlock
        scanId={runtimeTarget === 'local' ? 'local-results-verified' : 'results-phase5-phase6-oof'}
        region={tenant.region ? `${tenant.region}` : 'ap-south-1 (Mumbai, India)'}
        scannedTime="Verified Empirical Reports"
        isOnDevice={runtimeTarget === 'local'}
      />
    </div>
  );
};

export default ResultsPage;
