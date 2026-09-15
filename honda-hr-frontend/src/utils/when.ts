/**
 * How a timestamp is written, in one place.
 *
 * The History page localised its dates while the Administration page printed
 * the raw ISO string with its timezone offset, so the same event read as
 * "1 Sep 2026, 09:20" on one screen and "2026-09-01 09:20:00+05:00" on the
 * other. On a page whose whole job is to be a defensible record, two formats
 * for one clock is the kind of detail that makes a reader wonder what else
 * disagrees.
 */

/** "1 Sep 2026, 09:20". Falls back to the raw string if it will not parse. */
export function whenText(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * The same instant, with seconds, for the audit table.
 *
 * The record needs the extra precision — two actions inside the same minute
 * are common and their order is sometimes the point — but it must still be the
 * reader's own clock, not the server's offset printed raw.
 */
export function whenTextExact(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
