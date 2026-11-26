import { create } from 'zustand';
import { iamFindings } from '../types';
import rawFindings from '../mock/mockFindings.json';

interface FindingsState {
  findings: iamFindings[];
  approveFinding: (id: string) => { success: boolean; finding?: iamFindings };
  resetFindings: () => void;
  getPendingFindings: () => iamFindings[];
  getAppliedFindings: () => iamFindings[];
  getPendingCount: () => number;
}

const getInitialFindings = (): iamFindings[] => {
  return JSON.parse(JSON.stringify(rawFindings));
};

export const useFindingsStore = create<FindingsState>((set, get) => ({
  findings: getInitialFindings(),

  approveFinding: (id: string) => {
    let updatedItem: iamFindings | undefined;
    set((state) => {
      const next = state.findings.map((item) => {
        if (item.finding_id === id) {
          updatedItem = {
            ...item,
            auto_apply_status: 'APPLIED',
            status: 'APPLIED',
          };
          return updatedItem;
        }
        return item;
      });
      return { findings: next };
    });

    return {
      success: !!updatedItem,
      finding: updatedItem,
    };
  },

  resetFindings: () => {
    set({ findings: getInitialFindings() });
  },

  getPendingFindings: () => {
    return get().findings.filter(
      (f) => f.auto_apply_status === 'NEEDS_APPROVAL' || f.auto_apply_status === 'ESCALATED'
    );
  },

  getAppliedFindings: () => {
    return get().findings.filter(
      (f) => f.auto_apply_status === 'APPROVED' || f.auto_apply_status === 'APPLIED'
    );
  },

  getPendingCount: () => {
    return get().findings.filter(
      (f) => f.auto_apply_status === 'NEEDS_APPROVAL' || f.auto_apply_status === 'ESCALATED'
    ).length;
  },
}));

