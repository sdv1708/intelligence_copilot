import { Download, Info, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  asApiError,
  generateBrief,
  getBrief,
  getLatestBrief,
  listBriefs,
} from "../api/client";
import type { ApiError, BriefResponse, BriefStub, RequestOptions } from "../api/client";
import { briefFilename, briefToMarkdown, download } from "../brief";
import { formatMoment } from "../format";
import type { MeetingTasks } from "../hooks/useMeetingTasks";
import { BriefDocument } from "./BriefDocument";
import { TraceView } from "./TraceView";
import { Button, ErrorNote } from "./controls";

/**
 * The brief: generating one, reading one back, and showing how it was made.
 *
 * The state here is deliberately hand-rolled rather than another `useRequest`.
 * `useRequest` runs on mount and drops to `loading` on every reload, and both
 * are wrong for a brief: generating one is a POST that costs real tokens and
 * tens of seconds, so it must be button-driven, and the result it returns has
 * to *replace* what is on screen without any subsequent fetch overwriting it.
 * A refetch of the same brief id would come back without the trace, which is
 * the one thing a freshly generated brief has and a stored one does not.
 */

type State =
  | { status: "loading" }
  /** The meeting has never had a brief. Not an error — 404 is the answer. */
  | { status: "empty" }
  | { status: "failed"; error: ApiError }
  | {
      status: "ready";
      response: BriefResponse;
      /**
       * True for a brief this session generated. It is not the same as
       * `response.trace !== null` — it is *why* the trace is there — and it is
       * what lets the panel say "recalled from storage" rather than leaving the
       * absence of a trace to be inferred.
       */
      fresh: boolean;
    };

interface BriefPanelProps {
  meetingId: string;
  /** How many documents the meeting has. The API refuses a brief without one. */
  documents: number;
  tasks: MeetingTasks;
  /** A brief was generated; the sidebar's brief count has moved. */
  onGenerated: () => void;
}

/**
 * Which stored brief is on screen, and a way to any of the others.
 *
 * The interesting case is a brief the history does not list: one that failed to
 * store and has no id, or one just generated whose `listBriefs` refresh has not
 * landed. A `<select>` whose value matches no option does not go blank — the
 * browser falls back to the first one — so without an option of its own the
 * control would sit there labelling the brief below it with some *other*
 * brief's timestamp. It gets an explicit option instead, and the whole control
 * is hidden when there is nothing to choose between.
 */
function HistoryPicker({
  history,
  selectedId,
  unlistedLabel,
  disabled,
  onPick,
}: {
  history: BriefStub[];
  selectedId: string | null;
  /** What to call the selection when the history does not list it. */
  unlistedLabel: string;
  disabled: boolean;
  onPick: (briefId: string) => void;
}) {
  const known = history.some((stub) => stub.id === selectedId);
  if (history.length + (known ? 0 : 1) < 2) return null;

  return (
    <label className="flex min-w-0 items-center gap-2 text-xs text-muted">
      <span className="shrink-0">History</span>
      <select
        value={selectedId ?? ""}
        disabled={disabled}
        onChange={(event) => {
          // Re-picking what is already shown would refetch it, and for a brief
          // just generated the refetch comes back without the trace — the one
          // part of it that is not stored and cannot be got again.
          const picked = event.target.value;
          if (picked && picked !== selectedId) onPick(picked);
        }}
        className="min-w-0 rounded-md border border-line-strong bg-paper px-2 py-1.5 text-xs text-ink disabled:opacity-45"
      >
        {known ? null : <option value={selectedId ?? ""}>{unlistedLabel}</option>}
        {history.map((stub) => (
          <option key={stub.id} value={stub.id}>
            {formatMoment(stub.created_at)} · {stub.model}
          </option>
        ))}
      </select>
    </label>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-xs leading-relaxed text-muted">
      <Info size={13} strokeWidth={1.75} aria-hidden="true" className="mt-0.5 shrink-0" />
      <span className="min-w-0 flex-1">{children}</span>
    </p>
  );
}

export function BriefPanel({
  meetingId,
  documents,
  tasks,
  onGenerated,
}: BriefPanelProps) {
  const [state, setState] = useState<State>({ status: "loading" });
  /**
   * The picker's selection, held apart from `state` so it survives a load.
   * Deriving it from the response would blank the control for as long as the
   * fetch takes, and the control that says *which* brief you are looking at is
   * exactly the one that should not flicker while it changes.
   */
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [history, setHistory] = useState<BriefStub[]>([]);
  const [historyError, setHistoryError] = useState<ApiError | null>(null);
  const [generateError, setGenerateError] = useState<ApiError | null>(null);
  const [generating, setGenerating] = useState(false);

  /**
   * Which load owns the screen. Picking twice from the history quickly, or
   * generating while a load is in flight, would otherwise let the slower
   * response land last and win — and a stale winner here means the brief on
   * screen is not the one the control says it is.
   */
  const owner = useRef(0);

  const show = useCallback(
    async (load: (options: RequestOptions) => Promise<BriefResponse>, options: RequestOptions = {}) => {
      const token = ++owner.current;
      setState({ status: "loading" });
      try {
        const response = await load(options);
        if (token !== owner.current) return;
        setState({ status: "ready", response, fresh: false });
        setSelectedId(response.brief_id);
      } catch (cause) {
        if (token !== owner.current || options.signal?.aborted) return;
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        const error = asApiError(cause);
        // 404 from the latest-brief route is the answer to "is there one yet",
        // not a failure. Reporting it as an error would put a red box on every
        // meeting nobody has briefed.
        setState(
          error.status === 404
            ? { status: "empty" }
            : { status: "failed", error },
        );
      }
    },
    [],
  );

  const loadHistory = useCallback(
    async (options: RequestOptions = {}) => {
      try {
        setHistory(await listBriefs(meetingId, options));
        setHistoryError(null);
      } catch (cause) {
        if (options.signal?.aborted) return;
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        // Kept, not thrown away, but rendered only alongside a brief that did
        // load — if the meeting request failed too then this is the same
        // outage said twice, and the panel above already says it.
        setHistoryError(asApiError(cause));
      }
    },
    [meetingId],
  );

  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    void show((inner) => getLatestBrief(meetingId, inner), options);
    void loadHistory(options);
    return () => controller.abort();
  }, [meetingId, show, loadHistory]);

  async function generate() {
    setGenerateError(null);
    setGenerating(true);
    try {
      // Through `tasks.run` because the server holds this meeting's lock for
      // the whole run: the graph's retrieval step rewrites the index, so an
      // upload landing mid-run would block invisibly for tens of seconds.
      const response = await tasks.run(meetingId, () => generateBrief(meetingId));
      // Claim ownership so an in-flight history pick cannot overwrite the one
      // response in this component that cannot be fetched again.
      owner.current += 1;
      setState({ status: "ready", response, fresh: true });
      setSelectedId(response.brief_id);
      onGenerated();
      await loadHistory();
    } catch (cause) {
      setGenerateError(asApiError(cause));
    } finally {
      setGenerating(false);
    }
  }

  const busy = tasks.isBusy(meetingId);

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="mr-auto text-sm font-medium text-ink">Brief</h2>

        <HistoryPicker
          history={history}
          selectedId={selectedId}
          // Three different reasons the selection can be missing from the
          // history, and they are not interchangeable: it stored but the
          // refreshed list has not caught up, it never stored at all, or
          // nothing has resolved yet and there is no selection to name.
          unlistedLabel={
            selectedId !== null
              ? "Just generated"
              : state.status === "ready"
                ? "Not stored"
                : "Loading…"
          }
          disabled={state.status === "loading"}
          onPick={(briefId) => {
            setSelectedId(briefId);
            void show((options) => getBrief(briefId, options));
          }}
        />

        <Button
          variant="primary"
          onClick={() => void generate()}
          busy={generating}
          disabled={busy || documents === 0}
        >
          <Sparkles size={14} strokeWidth={1.75} aria-hidden="true" />
          {history.length ? "Generate again" : "Generate brief"}
        </Button>
      </div>

      {documents === 0 ? (
        <Note>
          A brief is written from the meeting&rsquo;s documents. Add at least one
          above.
        </Note>
      ) : null}

      {generateError ? (
        <ErrorNote error={generateError} onRetry={() => void generate()} />
      ) : null}

      {state.status === "loading" ? (
        <div aria-hidden="true" className="flex flex-col gap-3">
          <span className="h-3 w-48 animate-pulse rounded bg-line" />
          <span className="h-24 w-full animate-pulse rounded-xl bg-line" />
        </div>
      ) : null}

      {state.status === "empty" ? (
        <p className="rounded-xl border border-line bg-panel px-4 py-6 text-sm leading-relaxed text-muted">
          No brief yet. Generating one reads every document on this meeting and
          takes tens of seconds.
        </p>
      ) : null}

      {state.status === "failed" ? (
        <ErrorNote
          error={state.error}
          onRetry={() => void show((options) => getLatestBrief(meetingId, options))}
        />
      ) : null}

      {state.status === "ready" ? (
        <Result
          response={state.response}
          fresh={state.fresh}
          historyError={historyError}
        />
      ) : null}
    </section>
  );
}

function Result({
  response,
  fresh,
  historyError,
}: {
  response: BriefResponse;
  fresh: boolean;
  historyError: ApiError | null;
}) {
  return (
    <div className="flex flex-col gap-5">
      {/*
        `ok` and `warning` are independent, and both have to be read. A run that
        produced a brief and then failed to store it is `ok: true` with a
        warning — rendering only `ok` throws the warning away, rendering only
        the warning throws away a usable document.
      */}
      {response.warning ? (
        <p
          role="status"
          className={`rounded-lg border px-4 py-3 text-sm leading-relaxed ${
            response.ok ? "border-warn/40 text-warn" : "border-crit/40 text-crit"
          }`}
        >
          {response.ok
            ? `The brief was written but something went wrong afterwards: ${response.warning}`
            : response.warning}
        </p>
      ) : null}

      {response.brief ? (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <p className="mr-auto min-w-0 text-xs text-muted">
              {fresh ? "Generated just now" : "Recalled from storage"}
              {response.stored_at ? ` · stored ${formatMoment(response.stored_at)}` : null}
              {response.model ? ` · ${response.model}` : null}
            </p>
            <Button
              size="sm"
              onClick={() =>
                download(
                  briefFilename(response, "md"),
                  "text/markdown;charset=utf-8",
                  briefToMarkdown(response),
                )
              }
            >
              <Download size={13} strokeWidth={1.75} aria-hidden="true" />
              Markdown
            </Button>
            <Button
              size="sm"
              onClick={() =>
                download(
                  briefFilename(response, "json"),
                  "application/json;charset=utf-8",
                  // The whole response, not just the brief: the trace is the
                  // part worth keeping and it exists nowhere else once the
                  // page is closed.
                  `${JSON.stringify(response, null, 2)}\n`,
                )
              }
            >
              <Download size={13} strokeWidth={1.75} aria-hidden="true" />
              JSON
            </Button>
          </div>

          <BriefDocument brief={response.brief} />
        </>
      ) : null}

      {historyError ? (
        <Note>The brief history could not be read: {historyError.message}</Note>
      ) : null}

      {response.trace ? (
        <TraceView trace={response.trace} failedTasks={response.failed_tasks} />
      ) : (
        <Note>
          This brief was read back from the database, which stores the document
          and not the run behind it. Generate a new brief to see the plan, what
          each specialist found, and the order the nodes ran in.
        </Note>
      )}
    </div>
  );
}
