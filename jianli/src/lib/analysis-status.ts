const EXTERNAL_AI_PROVIDERS = new Set(["deepseek", "bailian", "qianwen", "zhipu"]);

export function taskUsedExternalAI(provider: unknown, fallbackUsed: unknown) {
  return EXTERNAL_AI_PROVIDERS.has(String(provider)) && fallbackUsed !== true;
}

export function sourceContextVerified(version: string | null | undefined) {
  return /^source-context-v(?:[2-9]|\d{2,})(?:-|$)/.test(version ?? "");
}
