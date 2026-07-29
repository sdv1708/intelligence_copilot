import { RotateCw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { Health } from "../api/client";
import type { RequestState } from "../hooks/useRequest";
import type { Severity, Signal } from "../status";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-x-4 gap-y-1 px-4 py-3 max-sm:grid-cols-1">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="min-w-0 text-sm text-ink">{children}</dd>
    </div>
  );
}

/** Machine-shaped values — paths, device names, model ids — get the mono face. */
function Value({ children }: { children: ReactNode }) {
  return <code className="text-[13px] break-all">{children}</code>;
}

const CALLOUT: Record<Severity, string> = {
  pending: "border-line text-muted",
  ok: "border-line text-muted",
  warn: "border-warn/40 text-warn",
  crit: "border-crit/40 text-crit",
};

function Callout({ signal, onRetry }: { signal: Signal; onRetry: () => void }) {
  return (
    <div
      role="status"
      className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${CALLOUT[signal.severity]}`}
    >
      <TriangleAlert
        size={16}
        strokeWidth={1.75}
        aria-hidden="true"
        className="mt-0.5 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{signal.label}</p>
        <p className="mt-1 text-sm leading-relaxed text-muted">{signal.detail}</p>
      </div>
      {signal.severity === "crit" ? (
        <button
          type="button"
          onClick={onRetry}
          className="flex shrink-0 items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-panel"
        >
          <RotateCw size={13} strokeWidth={1.75} aria-hidden="true" />
          Retry
        </button>
      ) : null}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="divide-y divide-line" aria-hidden="true">
      {[0, 1, 2, 3, 4, 5].map((row) => (
        <div key={row} className="flex items-center gap-4 px-4 py-3">
          <span className="h-3 w-28 animate-pulse rounded bg-line" />
          <span className="h-3 w-40 animate-pulse rounded bg-line" />
        </div>
      ))}
    </div>
  );
}

function Details({ health }: { health: Health }) {
  return (
    <dl className="divide-y divide-line">
      <Row label="Provider">
        <Value>{health.provider}</Value>
      </Row>
      <Row label="Model">
        <Value>{health.model}</Value>
      </Row>
      <Row label="API key">
        {health.has_api_key ? (
          "Present"
        ) : (
          <span className="text-warn">Missing</span>
        )}
      </Row>
      <Row label="Embeddings run on">
        <Value>{health.device}</Value>
      </Row>
      <Row label="Planning">
        {health.supervisor
          ? "Supervisor plans each brief with the model"
          : "Fixed plan — the supervisor is not planning with the model"}
      </Row>
      <Row label="Storage">
        <Value>{health.storage_dir}</Value>
        {health.storage_is_temporary ? (
          <p className="mt-1 text-xs text-warn">
            Temporary — nothing saved here survives a restart.
          </p>
        ) : null}
      </Row>
    </dl>
  );
}

interface StatusPanelProps {
  state: RequestState<Health>;
  signal: Signal;
  onRetry: () => void;
}

/**
 * The status view: the whole `/api/health` payload, not just the sidebar's
 * one-line reduction of it. It is what the shell has to show before meetings
 * exist, and it is the thing you check first when a brief will not generate.
 */
export function StatusPanel({ state, signal, onRetry }: StatusPanelProps) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Status</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          What the server is configured with, read from{" "}
          <code className="text-[13px]">/api/health</code>.
        </p>
      </div>

      {signal.detail ? <Callout signal={signal} onRetry={onRetry} /> : null}

      <section className="overflow-hidden rounded-xl border border-line bg-panel">
        {state.status === "loading" ? <Skeleton /> : null}
        {state.status === "ready" ? <Details health={state.data} /> : null}
        {state.status === "failed" ? (
          <p className="px-4 py-6 text-sm text-muted">
            No reading available while the API is unreachable.
          </p>
        ) : null}
      </section>

      {/*
        A build-state note. It goes when the phases it names have landed.
      */}
      <section className="rounded-xl border border-dashed border-line-strong px-4 py-4">
        <h2 className="text-[11px] font-medium tracking-wide text-faint uppercase">
          Not built yet
        </h2>
        <ul className="mt-2.5 flex flex-col gap-1.5 text-sm text-muted">
          <li>Briefs — the document, its history and the run trace.</li>
          <li>Q&amp;A — questions against one meeting, with citations.</li>
        </ul>
      </section>
    </div>
  );
}
