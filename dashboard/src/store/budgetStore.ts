import { create } from 'zustand';

interface BudgetState {
  k: number;
  setK: (k: number) => void;
}

export function clampK(value: unknown): number {
  const num = typeof value === 'number' ? value : parseInt(String(value), 10);
  if (isNaN(num)) return 3;
  return Math.max(1, Math.min(10, Math.round(num)));
}

export const useBudgetStore = create<BudgetState>((set) => ({
  k: 3,
  setK: (newK: number) => set({ k: clampK(newK) }),
}));

