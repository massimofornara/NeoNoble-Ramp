export class ExposureMonitor {
  exposure(asset: string, amount: string): Record<string, unknown> {
    const limit = Number(process.env[`${asset.toUpperCase()}_EXPOSURE_LIMIT`] ?? Number.POSITIVE_INFINITY);
    const value = Number(amount);
    return {
      asset,
      amount,
      limit: Number.isFinite(limit) ? String(limit) : "unbounded",
      withinLimit: value <= limit,
      utilization: Number.isFinite(limit) && limit > 0 ? value / limit : 0,
    };
  }
}
