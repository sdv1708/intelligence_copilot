/**
 * Display helpers shared by the meeting and material views.
 *
 * They live together because each one encodes something about the real data
 * rather than a preference: titles arrive untrimmed, timestamps are naive, and
 * character counts run to six figures.
 */

/**
 * Real rows hold `"check in "` and `"Q4 "` — the records layer stores what was
 * written. Trimming happens at display so the value on the wire stays the value
 * in the database, and a title that was only whitespace still renders as
 * something you can click.
 */
export function meetingTitle(title: string): string {
  return title.trim() || "Untitled meeting";
}

const DAY = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/**
 * `created_at` is a naive ISO timestamp the server wrote, so it parses as local
 * time. Anything that does not parse — a hand-edited row, a format change — is
 * shown as it came rather than as "Invalid Date".
 */
export function formatDay(value: string): string {
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? value : DAY.format(at);
}

const MOMENT = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/**
 * A timestamp with the time of day, for the brief history.
 *
 * `formatDay` is not enough there: the real database holds three briefs for one
 * meeting written within ninety seconds of each other, and a dropdown listing
 * them all as "11 Nov 2025" gives you no way to tell them apart.
 */
export function formatMoment(value: string): string {
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? value : MOMENT.format(at);
}

/** Six-figure character counts are unreadable without separators. */
export function formatCount(value: number): string {
  return value.toLocaleString();
}

export function plural(count: number, word: string): string {
  return `${formatCount(count)} ${word}${count === 1 ? "" : "s"}`;
}

/**
 * The sidebar's second line. Both counts zero means a meeting nothing has been
 * added to yet, which is worth saying rather than leaving blank.
 */
export function meetingSummary(materials: number, briefs: number): string {
  if (!materials && !briefs) return "Empty";
  const parts = [];
  if (materials) parts.push(plural(materials, "file"));
  if (briefs) parts.push(plural(briefs, "brief"));
  return parts.join(" · ");
}

/**
 * Split a comma-separated field into the array the API expects.
 *
 * The server joins it straight back into one column, so the round trip is
 * lossy for any value containing a comma. That is the storage format the
 * schema has had since long before this overhaul, and splitting the same way
 * here at least makes the UI agree with it.
 */
export function parseList(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}
