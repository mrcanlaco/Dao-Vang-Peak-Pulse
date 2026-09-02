import type { LlmConfig } from '../types';

export const LLM_CONFIG_STORAGE_KEY = 'dao_vang_llm_config';
export const LLM_CONFIG_CHANGED_EVENT = 'dao_vang_llm_config_changed';

export const DEFAULT_LLM_CONFIG: LlmConfig = {
  provider: 'openai',
  apiKey: '',
  modelId: 'antigravity/gemini-3.7-flash-tiered',
  baseUrl: 'https://proxy-ai.comaygiauco.com/v1',
  enabled: true,
};

export function readStoredLlmConfig(): LlmConfig {
  try {
    const saved = localStorage.getItem(LLM_CONFIG_STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved) as Partial<LlmConfig>;
      return {
        ...DEFAULT_LLM_CONFIG,
        ...parsed,
      };
    }
  } catch {
    // Fall back to the server-aligned default when localStorage is unavailable
    // or contains an older/invalid value.
  }
  return { ...DEFAULT_LLM_CONFIG };
}

export function hasStoredLlmConfig(): boolean {
  try {
    return localStorage.getItem(LLM_CONFIG_STORAGE_KEY) !== null;
  } catch {
    return false;
  }
}

export function saveStoredLlmConfig(config: LlmConfig): void {
  try {
    localStorage.setItem(LLM_CONFIG_STORAGE_KEY, JSON.stringify(config));
  } catch {
    // The in-memory state still remains usable if browser storage is blocked.
  }

  window.dispatchEvent(new CustomEvent<LlmConfig>(LLM_CONFIG_CHANGED_EVENT, {
    detail: config,
  }));
}
