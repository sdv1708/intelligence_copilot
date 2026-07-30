import type { Health } from "./api/client";
import type { RequestState } from "./hooks/useRequest";

/**
 * Reducing `/api/health` to one signal, in one place.
 *
 * The sidebar line and the status panel must never disagree about whether the
 * system is fine, so they read the same function rather than each deciding.
 */
export type Severity = "pending" | "ok" | "warn" | "crit";

export interface Signal {
  severity: Severity;
  /** Short enough for the sidebar footer. */
  label: string;
  /** One sentence saying what to do about it, or null when there is nothing. */
  detail: string | null;
}

/**
 * Ordered worst-first: an unreachable API makes every other reading stale, and
 * a missing key stops briefs outright, whereas temporary storage still works —
 * it just will not survive a restart.
 */
export function signalFor(state: RequestState<Health>): Signal {
  if (state.status === "loading") {
    return { severity: "pending", label: "Checking", detail: null };
  }

  if (state.status === "failed") {
    return {
      severity: "crit",
      label: state.error.isOffline ? "API offline" : "Health check failed",
      detail: state.error.message,
    };
  }

  const health = state.data;

  if (!health.has_api_key) {
    return {
      severity: "warn",
      label: "No API key",
      detail: `Set a key for ${health.provider} in .env to generate briefs and answers.`,
    };
  }

  if (health.storage_is_temporary) {
    return {
      severity: "warn",
      label: "Temporary storage",
      detail:
        "The configured data directory was not writable, so storage moved to a " +
        "temporary one. Nothing saved here survives a restart.",
    };
  }

  return {
    severity: "ok",
    label: `${health.provider} · ${health.model}`,
    detail: null,
  };
}
