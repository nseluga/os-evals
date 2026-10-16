// Shared helpers. Re-exported from src/index.mjs; connectors import from here to avoid an import cycle.

/** Error raised by a connector. `source` is the connector name, `code` a short machine-readable reason. */
export class SourceError extends Error {
  constructor(source, code, message) {
    super(message ?? `${source}: ${code}`);
    this.name = 'SourceError';
    this.source = source;
    this.code = code;
  }
}

/** Decimal string (or number) -> integer cents. Rounds half away from zero; throws on non-decimal input. */
export function minor(amountStr) {
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(amountStr).trim());
  if (!m) throw new TypeError(`minor: not a decimal amount: ${amountStr}`);
  const [, sign, whole, frac = ''] = m;
  let cents = Number(whole) * 100 + Number((frac + '00').slice(0, 2));
  if (frac.length > 2 && frac[2] >= '5') cents += 1;
  return sign && cents ? -cents : cents;
}

/** ISO timestamp -> YYYY-MM-DD calendar day in the given IANA timezone. Throws on a bad timestamp or tz. */
export function localDay(isoTs, tz) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(isoTs));
}

/** Mask credentials before a string is logged or stored. */
export function redact(str) {
  return String(str)
    .replace(/Bearer\s+[A-Za-z0-9._~+\/=-]+/g, 'Bearer [REDACTED]')
    .replace(/(sk_live|shpat)_[A-Za-z0-9]+/g, '$1_[REDACTED]');
}
