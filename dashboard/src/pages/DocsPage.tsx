import React, { useEffect, useState } from 'react';
import {
  BookOpen,
  Shield,
  Lock,
  Key,
  FileCode2,
  Copy,
  Check,
  Server,
  Cloud,
} from 'lucide-react';
import { getDocsSpec } from '../api';
import { DocsPayload } from '../types';
import { useWorkspaceStore } from '../store/workspaceStore';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';

const IAM_TERRAFORM_MODULE = `# ARGUS Least-Privilege Read-Only Cross-Account Audit Role
resource "aws_iam_role" "argus_audit_role" {
  name = "argus-audit-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { AWS = "arn:aws:iam::<YOUR_ARGUS_HOST_ACCOUNT>:root" }
      Condition = {
        StringEquals = { "sts:ExternalId" = "argus-dpdp-audit-external-id" }
      }
    }]
  })
}

# Read-only control plane policy (zero S3 GetObject / secret read access)
resource "aws_iam_role_policy_attachment" "argus_security_audit" {
  role       = aws_iam_role.argus_audit_role.name
  policy_arn = "arn:aws:iam::aws:policy/SecurityAudit"
}`;

export const DocsPage: React.FC = () => {
  const { runtimeTarget, workspaceRevision, tenant } = useWorkspaceStore();
  const [docs, setDocs] = useState<DocsPayload | null>(null);
  const [copiedTf, setCopiedTf] = useState(false);

  useEffect(() => {
    let mounted = true;
    getDocsSpec()
      .then((res) => {
        if (mounted) setDocs(res);
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, [runtimeTarget, workspaceRevision]);

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleCopyTf = () => {
    navigator.clipboard.writeText(IAM_TERRAFORM_MODULE);
    setCopiedTf(true);
    setTimeout(() => setCopiedTf(false), 2000);
  };

  return (
    <div className="w-full space-y-8 pb-12">
      {/* Header */}
      <section className="space-y-2 max-w-4xl">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold text-peacock bg-peacock/10 rounded-full">
            <BookOpen className="w-3.5 h-3.5" />
            <span>Engineering & Compliance Documentation</span>
          </span>
          <span className="text-xs text-ink-muted font-mono">DPDP Act 2023 • AWS ap-south-1</span>
        </div>
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          ARGUS Hybrid Sovereignty & Integration Reference
        </h1>
        <p className="text-[15px] text-ink-muted leading-relaxed">
          Complete technical specification covering the Hybrid Cloud Showcase + Local Execution split,
          least-privilege AWS IAM configuration, India DPDP Act 2023 Rego enforcement matrix, and closed Patch-IR schema.
        </p>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Sticky Section Index */}
        <aside className="lg:col-span-3 lg:sticky lg:top-4 p-4 bg-paper border border-ink-border rounded-xl space-y-2 text-xs">
          <p className="font-mono uppercase text-[10px] tracking-wider text-ink-faint font-semibold pb-1 border-b border-ink-border/60">
            Documentation Index
          </p>
          <nav className="flex flex-col space-y-1.5 font-medium text-ink-muted">
            <button type="button" onClick={() => scrollToSection('doc-hybrid')} className="text-left hover:text-peacock">
              1. Why Hybrid? (Zero Data Egress)
            </button>
            <button type="button" onClick={() => scrollToSection('doc-aws')} className="text-left hover:text-peacock">
              2. AWS Free Tier Topology
            </button>
            <button type="button" onClick={() => scrollToSection('doc-iam')} className="text-left hover:text-peacock">
              3. Least-Privilege IAM & iam_guard
            </button>
            <button type="button" onClick={() => scrollToSection('doc-dpdp')} className="text-left hover:text-peacock">
              4. DPDP Act 2023 Rule Matrix
            </button>
            <button type="button" onClick={() => scrollToSection('doc-patchir')} className="text-left hover:text-peacock">
              5. Closed 7-Op Patch-IR Spec
            </button>
          </nav>
        </aside>

        {/* Main Content */}
        <div className="lg:col-span-9 space-y-6">
          {/* 1. Hybrid Architecture */}
          <section id="doc-hybrid" className="p-6 bg-paper border border-ink-border rounded-2xl shadow-xs space-y-4">
            <div className="flex items-center gap-2 border-b border-ink-border/60 pb-3">
              <Server className="w-5 h-5 text-peacock" />
              <h2 className="font-headline text-xl font-medium text-ink">
                1. Why Hybrid? Compute Physics & DPDP Section 8 Sovereignty
              </h2>
            </div>
            <p className="text-xs text-ink-muted leading-relaxed">
              Hosting 2.6 GB quantized 4B models alongside customer AWS credentials on a shared public{' '}
              <code className="font-mono">t3.micro</code> (1 GB RAM) violates both RAM physics and India DPDP Act 2023 Section 8.
              Splitting ARGUS resolves both constraints cleanly:
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {(docs?.hybrid_layers || []).map((layer) => (
                <div key={layer.layer} className="p-3.5 bg-mist/40 border border-ink-border/80 rounded-xl space-y-1.5 text-xs">
                  <p className="font-semibold text-peacock">{layer.layer}</p>
                  <p className="font-mono text-[11px] text-ink">{layer.host}</p>
                  <p className="text-ink-muted leading-relaxed">{layer.role}</p>
                  <p className="pt-1 border-t border-ink-border/50 text-[11px] font-semibold text-forest">
                    {layer.data_boundary}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {/* 2. AWS Free Tier Topology */}
          <section id="doc-aws" className="p-6 bg-paper border border-ink-border rounded-2xl shadow-xs space-y-4">
            <div className="flex items-center gap-2 border-b border-ink-border/60 pb-3">
              <Cloud className="w-5 h-5 text-peacock" />
              <h2 className="font-headline text-xl font-medium text-ink">
                2. AWS Free Tier Infrastructure (<code className="font-mono text-base">ap-south-1</code> Mumbai)
              </h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-mist/40 border border-ink-border/70 rounded-lg space-y-1">
                <p className="font-semibold text-ink">
                  Amazon EC2 (<code className="font-mono">t3.micro</code>, Ubuntu 24.04)
                </p>
                <p className="text-ink-muted">
                  Runs <code className="font-mono">argus.service</code> (<code className="font-mono">deploy_dashboard.py 80</code>) serving the React SPA,{' '}
                  <code className="font-mono">/api/health</code>, <code className="font-mono">/api/benchmarks</code>, <code className="font-mono">/api/releases</code>, and synthetic demo sandbox inside AWS Free Tier.
                </p>
              </div>
              <div className="p-3 bg-mist/40 border border-ink-border/70 rounded-lg space-y-1">
                <p className="font-semibold text-ink">Amazon VPC & Security Group</p>
                <p className="text-ink-muted">
                  Restricts inbound traffic strictly to HTTP 80, HTTPS 443, and SSH 22 in Mumbai (<code className="font-mono">ap-south-1</code>).
                </p>
              </div>
              <div className="p-3 bg-mist/40 border border-ink-border/70 rounded-lg space-y-1">
                <p className="font-semibold text-ink">AWS IAM + STS ExternalId</p>
                <p className="text-ink-muted">
                  Least-privilege read-only <code className="font-mono">SecurityAudit</code> delegation checked by{' '}
                  <code className="font-mono">privacy/iam_guard.py</code> before any scan executes.
                </p>
              </div>
              <div className="p-3 bg-mist/40 border border-ink-border/70 rounded-lg space-y-1">
                <p className="font-semibold text-ink">Amazon S3 & CloudTrail</p>
                <p className="text-ink-muted">Control-plane audit targets for DPDP Rules 6, 6a, 7, 8, and 15 verification without downloading citizen objects.</p>
              </div>
            </div>
          </section>

          {/* 3. IAM Setup & iam_guard */}
          <section id="doc-iam" className="p-6 bg-paper border border-ink-border rounded-2xl shadow-xs space-y-4">
            <div className="flex items-center justify-between border-b border-ink-border/60 pb-3">
              <div className="flex items-center gap-2">
                <Key className="w-5 h-5 text-peacock" />
                <h2 className="font-headline text-xl font-medium text-ink">
                  3. Least-Privilege IAM Setup & Step Zero <code className="font-mono text-base">iam_guard</code>
                </h2>
              </div>
              <button
                type="button"
                onClick={handleCopyTf}
                className="text-xs font-medium text-peacock hover:underline flex items-center gap-1"
              >
                {copiedTf ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedTf ? 'Copied Terraform' : 'Copy Module'}</span>
              </button>
            </div>

            <pre className="p-4 bg-ink text-paper rounded-xl text-[11.5px] font-mono overflow-x-auto leading-relaxed">
              {IAM_TERRAFORM_MODULE}
            </pre>

            <div className="p-3.5 bg-garnet/5 border border-garnet/25 rounded-xl space-y-2 text-xs">
              <p className="font-semibold text-garnet flex items-center gap-1.5">
                <Lock className="w-4 h-4" />
                <span>
                  Forbidden Data-Plane Actions Hard-Blocked by <code className="font-mono">privacy/iam_guard.py</code>
                </span>
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(docs?.iam_guard_forbidden_sample || []).map((act) => (
                  <span key={act} className="px-2 py-0.5 bg-paper border border-garnet/30 rounded font-mono text-[11px] text-garnet">
                    {act}
                  </span>
                ))}
              </div>
            </div>
          </section>

          {/* 4. DPDP Matrix */}
          <section id="doc-dpdp" className="p-6 bg-paper border border-ink-border rounded-2xl shadow-xs space-y-4 overflow-x-auto">
            <div className="flex items-center gap-2 border-b border-ink-border/60 pb-3">
              <Shield className="w-5 h-5 text-peacock" />
              <h2 className="font-headline text-xl font-medium text-ink">
                4. India DPDP Act 2023 Rule Enforcement Matrix
              </h2>
            </div>

            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-ink-border text-ink-faint font-mono uppercase text-[11px]">
                  <th className="py-2 pr-3">DPDP Rule</th>
                  <th className="py-2 px-3">OPA Rego Policy</th>
                  <th className="py-2 px-3">Technical Fact Checked</th>
                  <th className="py-2 pl-3">Tier</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-border/50">
                {(docs?.dpdp_rule_matrix || []).map((row) => (
                  <tr key={row.dpdp_rule}>
                    <td className="py-2.5 pr-3 font-semibold text-ink">{row.dpdp_rule}</td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-peacock">
                      {row.rego_files.join(', ')}
                    </td>
                    <td className="py-2.5 px-3 text-ink-muted">{row.technical_check}</td>
                    <td className="py-2.5 pl-3 font-mono text-[11px] text-forest font-semibold">{row.tier}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* 5. Patch-IR Spec */}
          <section id="doc-patchir" className="p-6 bg-paper border border-ink-border rounded-2xl shadow-xs space-y-3">
            <div className="flex items-center gap-2 border-b border-ink-border/60 pb-3">
              <FileCode2 className="w-5 h-5 text-peacock" />
              <h2 className="font-headline text-xl font-medium text-ink">
                5. Closed 7-Operation Patch-IR Schema (<code className="font-mono text-base">remediate/patch_ir/schema.json</code>)
              </h2>
            </div>
            <p className="text-xs text-ink-muted">
              ARGUS never permits LLMs to emit arbitrary Terraform or shell scripts. Ollama M1 outputs strictly schema-validated Patch-IR verified by{' '}
              <code className="font-mono">gate_stub.py</code> + OPA Rego.
            </p>
            <pre className="p-4 bg-ink text-paper rounded-xl text-[11.5px] font-mono overflow-x-auto leading-relaxed">
              {JSON.stringify(docs?.patch_ir_schema || {}, null, 2)}
            </pre>
          </section>
        </div>
      </div>

      <FooterTitleBlock
        scanId={runtimeTarget === 'local' ? 'local-docs-dpdp-v2' : 'docs-dpdp-hybrid-v2'}
        region={tenant.region || 'ap-south-1 (Mumbai, India)'}
        scannedTime="Technical Spec v2.0"
        isOnDevice={runtimeTarget === 'local'}
      />
    </div>
  );
};

export default DocsPage;
