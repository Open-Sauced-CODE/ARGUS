import React, { useState, useMemo, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useFindingsStore } from '../store/findingsStore';
import { useWorkspaceStore } from '../store/workspaceStore';
import { approveFinding as apiApproveFinding, exportFindingPatchApi, getAuditExportUrl, getFindings } from '../api';
import { iamFindings } from '../types';
import { ConfidenceGauge } from '../components/approvals/ConfidenceGauge';
import { DiffViewer } from '../components/approvals/DiffViewer';
import { PatchIRViewer } from '../components/approvals/PatchIRViewer';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';
import { Check, ShieldCheck, ArrowRight, ExternalLink, Download, FileCode2 } from 'lucide-react';

const NUMBER_WORDS: Record<number, string> = {
  0: 'Zero',
  1: 'One',
  2: 'Two',
  3: 'Three',
  4: 'Four',
  5: 'Five',
  6: 'Six',
  7: 'Seven',
  8: 'Eight',
  9: 'Nine',
  10: 'Ten',
};

export const ApprovalsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { runtimeTarget, workspaceRevision, serverHealth, localStatus, tenant } = useWorkspaceStore();

  const findings = useFindingsStore((s) => s.findings);

  const [activeTab, setActiveTab] = useState<'pending' | 'applied'>('pending');
  const [confirmationMessage, setConfirmationMessage] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);

  // Filter queues
  const pendingQueue = useMemo(() => {
    return findings.filter(
      (f) => f.auto_apply_status === 'NEEDS_APPROVAL' || f.auto_apply_status === 'ESCALATED'
    );
  }, [findings]);

  const appliedQueue = useMemo(() => {
    return findings.filter(
      (f) => f.auto_apply_status === 'APPROVED' || f.auto_apply_status === 'APPLIED'
    );
  }, [findings]);

  const currentList = activeTab === 'pending' ? pendingQueue : appliedQueue;

  // Sync selected finding with URL query param ?finding=<id>
  const urlFindingId = searchParams.get('finding');
  const selectedFindingId = useMemo(() => {
    if (urlFindingId && currentList.some((f) => f.finding_id === urlFindingId)) {
      return urlFindingId;
    }
    // Also check if urlFindingId is in the other list and switch tab
    if (urlFindingId) {
      const inOther = findings.find((f) => f.finding_id === urlFindingId);
      if (inOther) {
        return urlFindingId;
      }
    }
    return currentList[0]?.finding_id || findings[0]?.finding_id || '';
  }, [urlFindingId, currentList, findings]);

  // If URL finding exists in a different tab, adjust active tab
  useEffect(() => {
    if (urlFindingId) {
      const isPending = pendingQueue.some((f) => f.finding_id === urlFindingId);
      const isApplied = appliedQueue.some((f) => f.finding_id === urlFindingId);
      if (isPending && activeTab !== 'pending') {
        setActiveTab('pending');
      } else if (isApplied && !isPending && activeTab !== 'applied') {
        setActiveTab('applied');
      }
    }
  }, [urlFindingId, pendingQueue, appliedQueue, activeTab]);

  const selectedFinding: iamFindings | undefined = useMemo(() => {
    return findings.find((f) => f.finding_id === selectedFindingId);
  }, [findings, selectedFindingId]);

  const handleSelectFinding = (findingId: string) => {
    setConfirmationMessage(null);
    setApprovalError(null);
    setExportMessage(null);
    setSearchParams({ finding: findingId }, { replace: true });
  };

  // Refresh findings on mount or when runtime target / workspace updates
  useEffect(() => {
    getFindings().catch((err) => console.warn('Could not refresh findings:', err));
  }, [runtimeTarget, workspaceRevision]);

  const handleApprove = async (id: string) => {
    setApprovalError(null);
    const nextIdx = pendingQueue.findIndex((f) => f.finding_id === id);
    try {
      await apiApproveFinding(id);
      setConfirmationMessage(
        runtimeTarget === 'local'
          ? 'Approved locally. Export .patch to apply to Terraform.'
          : 'Approved. Queued for deployment.'
      );

      // Select the next pending item
      const remainingPending = pendingQueue.filter((f) => f.finding_id !== id);
      if (remainingPending.length > 0) {
        const nextItem = remainingPending[nextIdx] || remainingPending[0];
        setSearchParams({ finding: nextItem.finding_id }, { replace: true });
      }
    } catch (err: any) {
      setApprovalError(err?.message || 'Could not approve finding.');
    }
  };

  // Headline from data: spell 1 to 10
  const pendingCount = pendingQueue.length;
  const countWord = NUMBER_WORDS[pendingCount] || String(pendingCount);
  const headline =
    pendingCount === 1
      ? 'One fix needs your approval.'
      : `${countWord} fixes need your approval.`;

  // Tier line formatting
  const getTierLine = (f: iamFindings) => {
    if (f.tier_used === 'T0') {
      return `Tier 0: ${f.generator_model || 'deterministic template'}, ${f.latency_ms || 0.4} ms`;
    }
    if (f.tier_used === 'T1') {
      return `Tier 1: ${f.generator_model || 'argus-m1-sft'}, local model`;
    }
    return 'Tier 3: human review';
  };

  const isCertified =
    runtimeTarget === 'local'
      ? Boolean(localStatus?.m2_status?.certified)
      : Boolean(serverHealth?.m2_certified);

  return (
    <div className="w-full space-y-6">
      {/* 1. Header Section */}
      <section className="space-y-1.5 max-w-2xl">
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          {headline}
        </h1>
        <p className="text-[15px] text-ink-muted">
          {!isCertified && appliedQueue.length === 0
            ? 'M2 LTT autonomy is OFF (awaiting calibration). All patches require explicit human architect review.'
            : 'The rest were applied automatically because their confidence cleared the threshold.'}
        </p>
      </section>

      {/* 2. Main Two-Pane Section with Hairline Divider (no boxed cards) */}
      <section
        aria-label="Approvals Workspace"
        className="grid grid-cols-1 lg:grid-cols-12 lg:divide-x lg:divide-ink-border border-y border-ink-border py-4 min-h-[520px]"
      >
        {/* Left Pane: Queue Tabs & List (col-span-5) */}
        <div className="lg:col-span-5 pr-0 lg:pr-6 flex flex-col justify-between">
          <div>
            {/* Underlined Text Tabs (not chips) */}
            <div className="flex items-center gap-6 border-b border-ink-border/60 pb-2">
              <button
                type="button"
                onClick={() => {
                  setActiveTab('pending');
                  setConfirmationMessage(null);
                  if (pendingQueue.length > 0) {
                    setSearchParams({ finding: pendingQueue[0].finding_id }, { replace: true });
                  }
                }}
                className={`text-[14px] font-medium transition-colors pb-1 border-b-2 -mb-[9px] ${
                  activeTab === 'pending'
                    ? 'border-peacock text-peacock font-semibold'
                    : 'border-transparent text-ink-muted hover:text-ink'
                }`}
              >
                Needs approval ({pendingQueue.length})
              </button>

              <button
                type="button"
                onClick={() => {
                  setActiveTab('applied');
                  setConfirmationMessage(null);
                  if (appliedQueue.length > 0) {
                    setSearchParams({ finding: appliedQueue[0].finding_id }, { replace: true });
                  }
                }}
                className={`text-[14px] font-medium transition-colors pb-1 border-b-2 -mb-[9px] ${
                  activeTab === 'applied'
                    ? 'border-peacock text-peacock font-semibold'
                    : 'border-transparent text-ink-muted hover:text-ink'
                }`}
              >
                Applied automatically ({appliedQueue.length})
              </button>
            </div>

            {/* Finding Ruled Rows */}
            {currentList.length === 0 ? (
              <div className="py-12 text-center text-ink-muted text-[13.5px]">
                {activeTab === 'pending'
                  ? 'All pending fixes have been reviewed.'
                  : 'No automatically applied fixes yet.'}
              </div>
            ) : (
              <div className="divide-y divide-ink-border/50 pt-1">
                {currentList.map((item) => {
                  const isSelected = item.finding_id === selectedFindingId;
                  const isEscalated = item.auto_apply_status === 'ESCALATED' || item.escalated;
                  const numericConf =
                    typeof item.m2_confidence === 'number'
                      ? item.m2_confidence
                      : typeof item.confidence === 'number'
                      ? item.confidence
                      : null;
                  const confPct = isEscalated
                    ? 'n/a'
                    : numericConf !== null
                    ? `${Math.round(numericConf * 100)}%`
                    : 'review';

                  return (
                    <div
                      key={item.finding_id}
                      onClick={() => handleSelectFinding(item.finding_id)}
                      className={`py-3 px-2 flex items-center justify-between gap-3 group cursor-pointer rounded-control transition-colors ${
                        isSelected
                          ? 'bg-ink-border/40 font-medium'
                          : 'hover:bg-ink-border/20'
                      }`}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          handleSelectFinding(item.finding_id);
                        }
                      }}
                    >
                      {/* Left: Title & Resource */}
                      <div className="flex-1 min-w-0 pr-2">
                        <p className={`text-[13.5px] truncate transition-colors ${
                          isSelected ? 'text-peacock font-semibold' : 'text-ink group-hover:text-peacock'
                        }`}>
                          {item.title}
                        </p>
                        <p className="font-mono text-[11px] text-ink-muted truncate mt-0.5">
                          {item.resource_id}
                        </p>
                      </div>

                      {/* Right: Confidence tabular */}
                      <div className="text-right flex-shrink-0">
                        <span className={`text-[13px] font-sans tabular-nums ${
                          isEscalated || numericConf === null
                            ? 'text-ink-faint font-mono text-[11px]'
                            : numericConf >= 0.95
                            ? 'text-verdigris font-semibold'
                            : 'text-saffron font-semibold'
                        }`}>
                          {confPct}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Quiet threshold line below the list */}
          <div className="pt-4 border-t border-ink-border/50 text-[12px] text-ink-muted">
            Auto-apply threshold: 95%{isCertified ? '' : ' (provisional)'}
          </div>
        </div>

        {/* Right Pane: Selected Finding Inspection (col-span-7) */}
        <div className="lg:col-span-7 pl-0 lg:pl-6 pt-6 lg:pt-0 flex flex-col justify-between">
          {selectedFinding ? (
            <div className="space-y-5">
              {/* a) Title, Rule, Severity, Resource ID */}
              <div className="space-y-1.5 pb-2 border-b border-ink-border/60">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="font-mono text-[12px] text-ink-muted">
                    {selectedFinding.finding_id}
                  </span>
                  <span className="text-[12px] font-medium text-ink bg-mist px-2 py-0.5 rounded">
                    Severity: {selectedFinding.severity.charAt(0).toUpperCase() + selectedFinding.severity.slice(1).toLowerCase()}
                  </span>
                </div>

                <h2 className="font-headline text-2xl text-ink font-medium">
                  {selectedFinding.title}
                </h2>

                <div className="flex items-center gap-2 text-[12.5px] text-ink-muted font-sans flex-wrap">
                  <span>Rule: {selectedFinding.rule_title || selectedFinding.rule_id}</span>
                  <span className="text-ink-border">•</span>
                  <span className="font-mono text-peacock">{selectedFinding.resource_id}</span>
                </div>
              </div>

              {/* b) Tier Line in Plain Text */}
              <div className="text-[13px] text-ink-muted font-sans">
                {getTierLine(selectedFinding)}
              </div>

              {/* c) Confidence Semicircle Gauge */}
              <div className="border-y border-ink-border/50 py-3">
                <ConfidenceGauge
                  confidence={selectedFinding.m2_confidence ?? (selectedFinding.confidence === 'n/a' ? null : (selectedFinding.confidence as number))}
                  threshold={selectedFinding.conformal_threshold || 0.95}
                  escalated={selectedFinding.auto_apply_status === 'ESCALATED' || selectedFinding.escalated}
                />
              </div>

              {/* d) Side-by-Side Code Diff */}
              <div>
                <DiffViewer
                  diff={selectedFinding.diff}
                  isEscalated={selectedFinding.auto_apply_status === 'ESCALATED' || selectedFinding.escalated}
                />
              </div>

              {/* e) Patch-IR Collapsible JSON */}
              <div>
                <PatchIRViewer patchIr={selectedFinding.patch_ir} />
              </div>

              {/* Confirmation & Error Notifications */}
              {confirmationMessage && (
                <div className="p-3 bg-verdigris/10 border border-verdigris/30 rounded-control text-verdigris text-[13px] font-medium flex items-center gap-2">
                  <Check className="w-4 h-4 flex-shrink-0" />
                  <span>{confirmationMessage}</span>
                </div>
              )}
              {approvalError && (
                <div className="p-3 bg-garnet/10 border border-garnet/30 rounded-control text-garnet text-[13px] font-medium">
                  {approvalError}
                </div>
              )}

              {/* f) Actions */}
              <div className="flex items-center gap-4 pt-2">
                {selectedFinding.auto_apply_status === 'NEEDS_APPROVAL' && (
                  <button
                    type="button"
                    onClick={() => handleApprove(selectedFinding.finding_id)}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-control bg-peacock text-paper font-medium text-[13.5px] hover:bg-peacock-hover active:bg-peacock-dark transition-colors shadow-sm"
                  >
                    <span>Approve and deploy</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                )}

                {selectedFinding.auto_apply_status === 'APPLIED' && (
                  <div className="inline-flex items-center gap-2 px-3.5 py-2 rounded-control bg-verdigris/15 text-verdigris font-medium text-[13px]">
                    <ShieldCheck className="w-4 h-4" />
                    <span>Applied to infrastructure</span>
                  </div>
                )}

                <Link
                  to={`/proof?finding=${selectedFinding.finding_id}`}
                  className="inline-flex items-center gap-1.5 text-[13px] font-medium text-peacock hover:underline px-2 py-1"
                >
                  <span>View privacy receipt</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </Link>

                {runtimeTarget === 'local' && (
                  <>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const res = await exportFindingPatchApi(selectedFinding.finding_id);
                          setExportMessage(`Exported patch to ${res.patch_path}`);
                        } catch (err: any) {
                          setExportMessage(err?.message || 'Export failed');
                        }
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control border border-ink-border bg-paper hover:bg-mist text-xs font-semibold text-ink"
                    >
                      <FileCode2 className="w-3.5 h-3.5 text-peacock" />
                      <span>Export .patch</span>
                    </button>
                    <a
                      href={getAuditExportUrl()}
                      download
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control border border-ink-border bg-paper hover:bg-mist text-xs font-semibold text-forest"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>DPDP Audit ZIP</span>
                    </a>
                  </>
                )}
              </div>

              {exportMessage && (
                <div className="p-2.5 bg-mist/60 border border-ink-border rounded-control text-xs font-mono text-ink">
                  {exportMessage}
                </div>
              )}
            </div>
          ) : (
            <div className="py-20 text-center text-ink-muted text-[14px]">
              Select a finding from the queue to inspect details.
            </div>
          )}
        </div>
      </section>

      {/* 3. Footer Title Block */}
      <FooterTitleBlock
        scanId={tenant.tenantId || 'scan-swasthya-mumbai-042'}
        region={tenant.region || 'ap-south-1'}
        scannedTime={tenant.connectedAt || 'Verified Local Queue'}
        isOnDevice={true}
      />
    </div>
  );
};

export default ApprovalsPage;
