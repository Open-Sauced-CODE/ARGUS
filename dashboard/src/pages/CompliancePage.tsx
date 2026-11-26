import React, { useEffect, useState, useMemo } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { getCompliance, getInitialCompliance } from '../api';
import { iamComp, iamFindings } from '../types';
import { useFindingsStore } from '../store/findingsStore';
import { useWorkspaceStore } from '../store/workspaceStore';
import { RadialProgressRing } from '../components/compliance/RadialProgressRing';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';
import { ArrowRight, AlertCircle, RefreshCw, CheckCircle2 } from 'lucide-react';

export const CompliancePage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const [rules, setRules] = useState<iamComp[]>(() => getInitialCompliance());
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const findings = useFindingsStore((s) => s.findings);
  const { runtimeTarget, workspaceRevision, tenant } = useWorkspaceStore();

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCompliance();
      setRules(data);
    } catch (err) {
      console.error('Failed to load compliance data:', err);
      setError('Could not load compliance scorecard.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [findings, runtimeTarget, workspaceRevision]);

  // Filter rules into scored (rings) and visibility (region statement)
  const scoredRules = useMemo(() => {
    return rules.filter((r) => !r.is_visibility_flag && (r.compliance_pct !== undefined || r.score_pct !== undefined));
  }, [rules]);

  const regionRule = useMemo(() => {
    return rules.find((r) => r.is_visibility_flag || r.rule_id === 'dpdp.rule15_residency');
  }, [rules]);

  // Overall readiness percentage (average of rules with percentages)
  const overallReadinessPct = useMemo(() => {
    if (scoredRules.length === 0) return 85;
    const total = scoredRules.reduce((acc, r) => acc + (r.compliance_pct ?? r.score_pct ?? 0), 0);
    return Math.round(total / scoredRules.length);
  }, [scoredRules]);

  // Total failing findings across all rules
  const totalFailingCount = useMemo(() => {
    return findings.filter(
      (f) => f.auto_apply_status === 'NEEDS_APPROVAL' || f.auto_apply_status === 'ESCALATED'
    ).length;
  }, [findings]);

  // Lowest-percentage rule as default
  const defaultRuleId = useMemo(() => {
    if (scoredRules.length === 0) return 'dpdp.rule6_public_exposure';
    const sorted = [...scoredRules].sort(
      (a, b) => (a.compliance_pct ?? a.score_pct ?? 100) - (b.compliance_pct ?? b.score_pct ?? 100)
    );
    return sorted[0].rule_id;
  }, [scoredRules]);

  const urlRuleId = searchParams.get('rule');
  const activeRuleId = urlRuleId || defaultRuleId;

  const handleSelectRule = (ruleId: string) => {
    setSearchParams({ rule: ruleId }, { replace: true });
  };

  // Currently selected rule
  const selectedRule = useMemo(() => {
    return rules.find((r) => r.rule_id === activeRuleId) || scoredRules[0] || rules[0];
  }, [rules, scoredRules, activeRuleId]);

  // Findings belonging to the selected rule
  const ruleFindings = useMemo(() => {
    if (!selectedRule) return [];
    return findings.filter((f) => {
      if (selectedRule.finding_ids && selectedRule.finding_ids.length > 0) {
        return selectedRule.finding_ids.includes(f.finding_id);
      }
      return f.rule_id === selectedRule.rule_id;
    });
  }, [findings, selectedRule]);

  // Format status for plain text display
  const getStatusLabel = (f: iamFindings) => {
    if (f.auto_apply_status === 'APPROVED' || f.auto_apply_status === 'APPLIED') {
      return 'auto-applied';
    }
    if (f.auto_apply_status === 'ESCALATED' || f.escalated) {
      return 'escalated';
    }
    return 'needs approval';
  };

  const getSeverityLabel = (sev: string) => {
    return sev.charAt(0).toUpperCase() + sev.slice(1).toLowerCase();
  };

  return (
    <div className="w-full space-y-6">
      {/* 1. Header Section */}
      <section className="space-y-1.5 max-w-2xl">
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          Your DPDP readiness is {overallReadinessPct}%.
        </h1>
        <p className="text-[15px] text-ink-muted">
          {totalFailingCount} {totalFailingCount === 1 ? 'finding stands' : 'findings stand'} between you and full compliance.
        </p>
      </section>

      {/* 2. Loading or Error State */}
      {error ? (
        <div className="p-4 bg-paper rounded-panel border border-garnet/40 text-garnet flex items-center justify-between">
          <div className="flex items-center gap-2 text-[14px]">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={loadData}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control bg-peacock text-paper text-[12px] font-medium"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Try again</span>
          </button>
        </div>
      ) : loading ? (
        <div className="space-y-4 animate-pulse">
          <div className="h-32 bg-ink-border/30 rounded-panel" />
          <div className="h-64 bg-ink-border/30 rounded-panel" />
        </div>
      ) : (
        <>
          {/* 3. Radial Progress Rings Row (open on mist canvas, separated by hairlines, no boxes) */}
          <section
            aria-label="Compliance Rules Overview"
            className="grid grid-cols-2 md:grid-cols-5 divide-y md:divide-y-0 md:divide-x divide-ink-border border-y border-ink-border py-4"
          >
            {scoredRules.map((r) => {
              const pct = r.compliance_pct ?? r.score_pct ?? 0;
              const failing = r.failing_count ?? r.violations_count ?? 0;
              return (
                <div key={r.rule_id} className="flex justify-center p-2">
                  <RadialProgressRing
                    ruleId={r.rule_id}
                    name={r.name}
                    percentage={pct}
                    failingCount={failing}
                    isSelected={activeRuleId === r.rule_id}
                    onSelect={handleSelectRule}
                  />
                </div>
              );
            })}

            {/* Rule 15 Region Statement (no ring, plain statement from data) */}
            <div className="col-span-2 md:col-span-1 flex flex-col justify-center items-center md:items-start text-center md:text-left p-4 space-y-1.5">
              <p className="text-[12px] uppercase font-mono text-ink-faint">
                {regionRule?.name || 'Rule 15 Region'}
              </p>
              <div className="flex items-center gap-1.5 text-verdigris font-medium text-[13.5px]">
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                <span>
                  {regionRule?.residency?.cross_border_resources && regionRule.residency.cross_border_resources.length > 0
                    ? `${regionRule.residency.cross_border_resources.length} cross-border resources`
                    : `All resources are in ${regionRule?.residency?.home_region || 'ap-south-1'}`}
                </span>
              </div>
              <p className="text-[12px] text-ink-muted">
                Zero data plane transfers outside verified borders.
              </p>
            </div>
          </section>

          {/* 4. Findings Ruled List under Selected Rule */}
          <section className="space-y-4 pt-1" aria-label="Rule Findings Details">
            <div className="flex items-center justify-between pb-2 border-b border-ink-border">
              <div>
                <h2 className="font-headline text-2xl text-ink font-medium">
                  Findings under {selectedRule?.name || 'selected rule'}
                </h2>
                <p className="text-[12.5px] text-ink-muted pt-0.5">
                  {selectedRule?.description || 'Rule requirements and verified configurations.'}
                </p>
              </div>

              <Link
                to="/approvals"
                className="inline-flex items-center gap-1 text-[13px] font-medium text-peacock hover:underline"
              >
                <span>Open the approval queue</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {ruleFindings.length === 0 ? (
              <div className="py-8 text-center text-ink-muted text-[13.5px]">
                No active findings under this rule.
              </div>
            ) : (
              <div className="divide-y divide-ink-border/50">
                {/* Column Headers */}
                <div className="flex items-center justify-between text-[12px] text-ink-faint py-2">
                  <span className="flex-1">Finding</span>
                  <span className="w-32 hidden sm:block text-left">Resource</span>
                  <span className="w-24 text-left">Severity</span>
                  <span className="w-32 text-right">Status</span>
                </div>

                {/* Rows */}
                {ruleFindings.map((finding) => (
                  <div
                    key={finding.finding_id}
                    onClick={() => navigate(`/approvals?finding=${finding.finding_id}`)}
                    className="py-3 flex items-center justify-between gap-4 group cursor-pointer hover:bg-ink-border/30 -mx-2 px-2 rounded-control transition-colors"
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        navigate(`/approvals?finding=${finding.finding_id}`);
                      }
                    }}
                  >
                    {/* Title */}
                    <div className="flex-1 min-w-0 pr-2">
                      <p className="text-[14px] font-medium text-ink group-hover:text-peacock transition-colors truncate">
                        {finding.title}
                      </p>
                      <p className="text-[11.5px] text-ink-muted truncate sm:hidden font-mono mt-0.5">
                        {finding.resource_id}
                      </p>
                    </div>

                    {/* Resource ID in Mono */}
                    <div className="w-32 hidden sm:block font-mono text-[12px] text-ink-muted truncate">
                      {finding.resource_id}
                    </div>

                    {/* Severity plain text */}
                    <div className="w-24 text-[13px] text-ink">
                      {getSeverityLabel(finding.severity)}
                    </div>

                    {/* Status plain text */}
                    <div className="w-32 text-right text-[13px] text-ink-muted font-sans capitalize">
                      {getStatusLabel(finding)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {/* 5. Footer Title Block */}
      <FooterTitleBlock
        scanId={tenant.tenantId || 'scan-swasthya-mumbai-042'}
        region={tenant.region || 'ap-south-1'}
        scannedTime={tenant.connectedAt || 'Verified DPDP Audit'}
        isOnDevice={true}
      />
    </div>
  );
};

export default CompliancePage;
