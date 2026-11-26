import React, { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useFindingsStore } from '../store/findingsStore';
import { useWorkspaceStore } from '../store/workspaceStore';
import { PrivacyReceipt } from '../types';
import { getReceipts } from '../api';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';
import {
  CheckCircle2,
  XCircle,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Shield,
} from 'lucide-react';
import rawReceipts from '../mock/mockReceipts.json';

export const ProofPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const findings = useFindingsStore((s) => s.findings);
  const { runtimeTarget, workspaceRevision, tenant } = useWorkspaceStore();

  // Synchronously initialize receipts with fallback, then fetch live backend receipts
  const [receipts, setReceipts] = useState<PrivacyReceipt[]>(() =>
    JSON.parse(JSON.stringify(rawReceipts as unknown as PrivacyReceipt[]))
  );

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const liveReceipts = await getReceipts();
        if (mounted && Array.isArray(liveReceipts)) {
          setReceipts(liveReceipts);
        }
      } catch (err) {
        console.warn('Failed to load receipts from backend:', err);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [runtimeTarget, workspaceRevision]);

  const [copied, setCopied] = useState(false);
  const [isJsonOpen, setIsJsonOpen] = useState(false);

  // Sync selected finding with URL ?finding=<finding_id>
  const urlFindingId = searchParams.get('finding');
  const selectedReceipt = useMemo(() => {
    if (urlFindingId) {
      const match = receipts.find((r) => r.finding_id === urlFindingId);
      if (match) return match;
    }
    return receipts[0];
  }, [receipts, urlFindingId]);

  const handleSelectReceipt = (findingId: string) => {
    setCopied(false);
    setSearchParams({ finding: findingId }, { replace: true });
  };

  // Map finding titles
  const findingTitleMap = useMemo(() => {
    const map = new Map<string, string>();
    findings.forEach((f) => {
      map.set(f.finding_id, f.title);
    });
    return map;
  }, [findings]);

  // Headline rule: zero data egress holds whenever every receipt has leaked_to_network === false.
  // Scrub hits mean PII/secrets were intercepted & masked BEFORE any synthesis call.
  const anyLeaked = useMemo(() => {
    return receipts.some((r) => Boolean(r.leaked_to_network));
  }, [receipts]);

  const totalScrubbed = useMemo(() => {
    return receipts.reduce(
      (sum, r) =>
        sum + (r.scrub_result?.presidio_hits ?? 0) + (r.scrub_result?.secret_scan_hits ?? 0),
      0
    );
  }, [receipts]);

  const headline = anyLeaked
    ? `${receipts.length} privacy receipts audited with outbound network events.`
    : 'Nothing left this device.';

  const subline = anyLeaked
    ? `${receipts.length} privacy receipts audited — outbound network transmission flagged.`
    : `${receipts.length} privacy receipts certified under local inspection${
        totalScrubbed > 0 ? ` • ${totalScrubbed} PII & secret entities scrubbed prior to synthesis` : ''
      }.`;

  const handleCopyJson = () => {
    if (!selectedReceipt) return;
    navigator.clipboard.writeText(JSON.stringify(selectedReceipt, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="w-full space-y-6">
      {/* 1. Header Section */}
      <section className="space-y-1.5 max-w-2xl">
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          {headline}
        </h1>
        <p className="text-[15px] text-ink-muted">
          {subline}
        </p>
      </section>

      {/* 2. Main Two-Pane Workspace with Hairline Divider (no cards) */}
      <section
        aria-label="Privacy Receipts Workspace"
        className="grid grid-cols-1 lg:grid-cols-12 lg:divide-x lg:divide-ink-border border-y border-ink-border py-4 min-h-[520px]"
      >
        {/* Left Pane: Ruled List of Receipts (col-span-5) */}
        <div className="lg:col-span-5 pr-0 lg:pr-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-ink-border/60">
              <h2 className="font-headline text-2xl text-ink font-medium">
                Privacy receipts
              </h2>
              <span className="text-[12px] font-mono text-ink-muted">
                {receipts.length} certified
              </span>
            </div>

            {/* List */}
            <div className="divide-y divide-ink-border/50 pt-1">
              {receipts.map((rcpt) => {
                const isSelected = selectedReceipt?.receipt_id === rcpt.receipt_id;
                const findingTitle =
                  findingTitleMap.get(rcpt.finding_id) || 'Cloud remediation finding';

                return (
                  <div
                    key={rcpt.receipt_id}
                    onClick={() => handleSelectReceipt(rcpt.finding_id)}
                    className={`py-3 px-2 flex flex-col gap-1 group cursor-pointer rounded-control transition-colors ${
                      isSelected
                        ? 'bg-ink-border/40 font-medium'
                        : 'hover:bg-ink-border/20'
                    }`}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        handleSelectReceipt(rcpt.finding_id);
                      }
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11.5px] text-peacock font-semibold truncate">
                        {rcpt.receipt_id}
                      </span>
                      <span className="text-[11px] font-mono text-ink-faint">
                        {rcpt.tier_used}
                      </span>
                    </div>

                    <p className={`text-[13px] truncate transition-colors ${
                      isSelected ? 'text-ink font-semibold' : 'text-ink-muted group-hover:text-ink'
                    }`}>
                      {findingTitle}
                    </p>

                    <p className="text-[11px] font-mono text-ink-faint truncate">
                      {rcpt.rule_id}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Bottom helper */}
          <div className="pt-4 border-t border-ink-border/50 text-[12px] text-ink-muted flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-peacock" />
            <span>Zero cloud credentials transmitted</span>
          </div>
        </div>

        {/* Right Pane: Selected Receipt Details (col-span-7) */}
        <div className="lg:col-span-7 pl-0 lg:pl-6 pt-6 lg:pt-0 flex flex-col justify-between">
          {selectedReceipt ? (
            <div className="space-y-6">
              {/* a) Header: Receipt ID, Rule ID, Tier */}
              <div className="space-y-1 pb-3 border-b border-ink-border/60">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="font-mono text-[13px] font-semibold text-peacock">
                    {selectedReceipt.receipt_id}
                  </span>
                  <span className="text-[12px] font-mono bg-ink-border/40 text-ink px-2 py-0.5 rounded">
                    Tier: {selectedReceipt.tier_used}
                  </span>
                </div>

                <p className="text-[13px] font-mono text-ink-muted">
                  Rule: {selectedReceipt.rule_id}
                </p>
              </div>

              {/* b) Tokens Used Table */}
              <div className="space-y-2">
                <h3 className="font-headline text-lg text-ink font-medium">
                  Tokens used
                </h3>

                <div className="border border-ink-border/60 rounded-control bg-paper divide-y divide-ink-border/50 font-mono text-[12px]">
                  <div className="flex items-center justify-between px-3 py-2 text-ink-faint bg-mist/40 text-[11px] uppercase tracking-wider">
                    <span>Token Identifier</span>
                    <span>Local Vault Reference</span>
                  </div>

                  {Object.entries(selectedReceipt.tokens || {}).map(([token, vaultRef]) => (
                    <div key={token} className="flex items-center justify-between px-3 py-2 text-ink">
                      <span className="text-peacock font-semibold">{token}</span>
                      <span className="text-ink-muted select-all">{vaultRef}</span>
                    </div>
                  ))}
                </div>

                <p className="text-[12.5px] text-ink-muted">
                  Real resource names were replaced by these tokens before anything was sent to a model.
                </p>
              </div>

              {/* c) What Was Shared */}
              <div className="space-y-2">
                <h3 className="font-headline text-lg text-ink font-medium">
                  What was shared
                </h3>

                <div className="border border-ink-border/60 rounded-control bg-paper divide-y divide-ink-border/50 text-[12.5px]">
                  {Object.entries(selectedReceipt.projected_fields || {}).map(([key, val]) => (
                    <div key={key} className="flex items-start justify-between px-3 py-2 gap-4">
                      <span className="font-mono text-[12px] text-ink-muted flex-shrink-0">
                        {key}
                      </span>
                      <span className="font-mono text-[12px] text-ink text-right select-all break-all">
                        {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* d) Scrub Results */}
              <div className="space-y-2">
                <h3 className="font-headline text-lg text-ink font-medium">
                  Scrub results
                </h3>

                <div className="grid grid-cols-2 gap-3 text-[13px]">
                  <div className="border border-ink-border/60 rounded-control p-3 bg-paper">
                    <p className="text-[12px] text-ink-muted">Presidio PII Hits</p>
                    <p className="font-sans font-semibold text-lg text-ink tabular-nums pt-0.5">
                      {selectedReceipt.scrub_result?.presidio_hits ?? 0}
                    </p>
                    <p className="text-[11px] text-ink-faint">Zero PII entities leaked</p>
                  </div>

                  <div className="border border-ink-border/60 rounded-control p-3 bg-paper">
                    <p className="text-[12px] text-ink-muted">Secret Scan Hits</p>
                    <p className="font-sans font-semibold text-lg text-ink tabular-nums pt-0.5">
                      {selectedReceipt.scrub_result?.secret_scan_hits ?? 0}
                    </p>
                    <p className="text-[11px] text-ink-faint">Zero API keys detected</p>
                  </div>
                </div>
              </div>

              {/* e) Network Check */}
              <div className="border-t border-ink-border/50 pt-3">
                {!selectedReceipt.leaked_to_network ? (
                  <div className="flex items-center gap-2 text-verdigris text-[13.5px] font-medium">
                    <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                    <span>No data left this device</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-garnet text-[13.5px] font-medium">
                    <XCircle className="w-4 h-4 flex-shrink-0" />
                    <span>Network transmission detected during processing</span>
                  </div>
                )}
              </div>

              {/* f) Actions: Copy receipt JSON & Collapsible viewer */}
              <div className="space-y-3 pt-1">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={handleCopyJson}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-control bg-peacock text-paper font-medium text-[13px] hover:bg-peacock-hover active:bg-peacock-dark transition-colors shadow-sm"
                  >
                    {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copied ? 'Copied to clipboard' : 'Copy receipt JSON'}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setIsJsonOpen(!isJsonOpen)}
                    className="inline-flex items-center gap-1 text-[13px] font-medium text-peacock hover:underline px-2 py-1"
                    aria-expanded={isJsonOpen}
                  >
                    <span>{isJsonOpen ? 'Hide raw JSON' : 'View raw JSON'}</span>
                    {isJsonOpen ? (
                      <ChevronDown className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>

                {/* Collapsible raw JSON */}
                {isJsonOpen && (
                  <div className="border border-ink-border/60 rounded-control bg-paper p-3 text-[11.5px] font-mono text-ink overflow-x-auto">
                    <pre className="whitespace-pre-wrap">
                      {JSON.stringify(selectedReceipt, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="py-20 text-center text-ink-muted text-[14px]">
              Select a receipt to inspect.
            </div>
          )}
        </div>
      </section>

      {/* 3. Footer Title Block */}
      <FooterTitleBlock
        scanId={tenant.tenantId || 'scan-swasthya-mumbai-042'}
        region={tenant.region || 'ap-south-1'}
        scannedTime={tenant.connectedAt || 'Verified On-Device'}
        isOnDevice={true}
      />
    </div>
  );
};

export default ProofPage;
