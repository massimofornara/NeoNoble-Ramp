export class MarginEngine {
  requirement(notionalUsd: string): Record<string, unknown> {
    const rate = Number(process.env.MARGIN_REQUIREMENT_RATE ?? 0.1);
    return {
      notionalUsd,
      marginRequiredUsd: String(Number(notionalUsd) * rate),
      rate,
    };
  }
}
