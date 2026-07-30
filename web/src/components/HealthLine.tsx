import type { Severity, Signal } from "../status";

const DOT: Record<Severity, string> = {
  pending: "bg-faint",
  ok: "bg-ok",
  warn: "bg-warn",
  crit: "bg-crit",
};

/**
 * Severity is carried by shape as well as colour — the pending state pulses and
 * the others do not — so the line still reads on a monochrome display.
 */
export function SeverityDot({ severity }: { severity: Severity }) {
  return (
    <span
      aria-hidden="true"
      className={`size-2 shrink-0 rounded-full ${DOT[severity]} ${
        severity === "pending" ? "animate-pulse" : ""
      }`}
    />
  );
}

/** The one-line reading pinned to the bottom of the sidebar. */
export function HealthLine({ signal }: { signal: Signal }) {
  return (
    <div
      className="flex min-w-0 items-center gap-2 text-xs text-muted"
      title={signal.detail ?? undefined}
    >
      <SeverityDot severity={signal.severity} />
      <span className="truncate">{signal.label}</span>
    </div>
  );
}
