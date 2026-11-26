import React from 'react';
import { useLocation, Link } from 'react-router-dom';

interface PlaceholderProps {
  title: string;
  description: string;
}

const PlaceholderView: React.FC<PlaceholderProps> = ({ title, description }) => {
  const location = useLocation();

  return (
    <div className="bg-paper rounded-panel border border-ink-border/60 p-12 shadow-soft min-h-[450px] flex flex-col items-center justify-center text-center space-y-4">
      <div className="w-12 h-12 rounded-full bg-mist flex items-center justify-center text-peacock font-headline text-xl">
        §
      </div>
      <h1 className="font-headline text-3xl text-ink">{title}</h1>
      <p className="text-[14px] text-ink-muted max-w-md">
        {description}
      </p>
      <div className="pt-4">
        <Link
          to="/"
          className="text-[13px] font-medium text-peacock hover:underline inline-flex items-center gap-1.5"
        >
          ← Return to Overview
        </Link>
      </div>
      <div className="text-[12px] font-mono text-ink-faint">
        Path: {location.pathname}
      </div>
    </div>
  );
};

export const ProofPage: React.FC = () => (
  <PlaceholderView
    title="Privacy & Verification Proof"
    description="Zero-data-plane privacy receipts, Presidio scrubbing audit logs, and token vault mapping proofs."
  />
);
