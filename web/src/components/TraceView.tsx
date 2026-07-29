import { Check, Radar, X } from "lucide-react";

import type { FindingOut, Trace } from "../api/client";
import { formatCount, plural } from "../format";

/**
 * How a run produced what it produced.
 *
 * This is the headline of Phase 5 and the thing the Streamlit UI could only
 * render as a wall of monospace inside a collapsed expander: what the
 * supervisor decided to look for, what each specialist came back with, which
 * enquiries failed, and the order the nodes ran in.
 *
 * Every block is conditional, which is what lets a Q&A trace through the same
 * component: `api/translate.py`'s `qa_response` builds a `Trace` from notes and
 * a chunk count alone, so the plan and findings blocks simply do not render and
 * the timeline carries it. The one thing that did *not* degrade was the header —
 * an empty `plan_source` used to render as "Plan source: unknown", a sentence
 * about planning on a run that never planned — so the header is conditional too.
 */

/** `plan_source` is one of three values from `agents/planner.py`. */
const PLAN_SOURCE: Record<string, string> = {
  supervisor: "The supervisor planned this run with the model",
  default: "The standing roster — the supervisor did not plan this run",
  caller: "A plan supplied by the caller",
};

/**
 * Hits and neighbours, side by side rather than stacked.
 *
 * They are not the same quantity: a hit matched the query, a neighbour was
 * pulled in only because it sits beside one. Stacking them into a single bar
 * would read as "the search found this much", which is exactly the overstatement
 * `api/schemas.py` separates the two counts to avoid.
 *
 * The form is emphasis, not categorical — hits are the subject and neighbours
 * are context — so it is one hue against the de-emphasis neutral rather than
 * two competing hues. That pairing is safe under every colour-vision deficiency
 * because only one of the two carries a hue at all, and both bars are
 * direct-labelled, so the counts never depend on telling the colours apart.
 */
function Bar({ value, scale, tone }: { value: number; scale: number; tone: string }) {
  return (
    <span
      aria-hidden="true"
      className={`block h-1.5 rounded-full ${tone}`}
      // Zero has to stay visible as a zero-width rule rather than vanishing,
      // or "found nothing" looks the same as "was not run".
      style={{ width: `${scale > 0 ? (value / scale) * 100 : 0}%`, minWidth: "2px" }}
    />
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="h-1.5 w-6 rounded-full bg-accent" />
        Hits — matched the query
      </span>
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="h-1.5 w-6 rounded-full bg-line-strong" />
        Neighbours — pulled in beside a hit
      </span>
    </div>
  );
}

function Finding({ finding, scale }: { finding: FindingOut; scale: number }) {
  const Icon = finding.ok ? Check : X;

  return (
    <li className="flex flex-col gap-2 px-4 py-3">
      <div className="flex items-start gap-2.5">
        <Icon
          size={14}
          strokeWidth={2}
          aria-hidden="true"
          className={`mt-1 shrink-0 ${finding.ok ? "text-ok" : "text-crit"}`}
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-ink">{finding.name}</p>
          <p className="mt-0.5 text-xs leading-relaxed break-words text-muted">
            {finding.query.trim() ? `“${finding.query}”` : "Swept the whole meeting"}
          </p>
        </div>
      </div>

      {finding.ok ? (
        <div className="flex flex-col gap-1 pl-6">
          <div className="flex items-center gap-2">
            <span className="w-24 shrink-0 text-xs text-muted tabular-nums">
              {formatCount(finding.hits)} hits
            </span>
            <span className="min-w-0 flex-1">
              <Bar value={finding.hits} scale={scale} tone="bg-accent" />
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-24 shrink-0 text-xs text-muted tabular-nums">
              {formatCount(finding.neighbours)} neighbours
            </span>
            <span className="min-w-0 flex-1">
              <Bar value={finding.neighbours} scale={scale} tone="bg-line-strong" />
            </span>
          </div>
        </div>
      ) : (
        <p className="pl-6 text-xs leading-relaxed text-crit">
          {finding.error ?? "Failed for an unstated reason."}
        </p>
      )}
    </li>
  );
}

/**
 * The node timeline.
 *
 * Every note is written by `agents/state.py:note` as `"phase: what happened"`,
 * so splitting on the first colon recovers the phase and lets it be read as a
 * column. A note that does not follow the convention keeps its whole text.
 */
function Timeline({ notes }: { notes: string[] }) {
  return (
    <ol className="flex flex-col">
      {notes.map((note, index) => {
        const at = note.indexOf(": ");
        const phase = at > 0 ? note.slice(0, at) : null;
        const rest = at > 0 ? note.slice(at + 2) : note;

        return (
          <li key={`${note}-${index}`} className="flex gap-3">
            {/* The rule is drawn by the item, not between items, so the last
                one stops at its own dot instead of trailing into nothing. */}
            <div className="flex w-3 shrink-0 flex-col items-center">
              <span
                aria-hidden="true"
                className="mt-1.5 size-1.5 shrink-0 rounded-full bg-line-strong"
              />
              {index < notes.length - 1 ? (
                <span aria-hidden="true" className="w-px flex-1 bg-line" />
              ) : null}
            </div>
            <div className="min-w-0 flex-1 pb-3">
              {phase ? (
                <p className="text-[11px] tracking-wide text-faint uppercase">{phase}</p>
              ) : null}
              <p className="text-xs leading-relaxed break-words text-muted">{rest}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2.5">
      <h4 className="text-[11px] font-medium tracking-wide text-faint uppercase">
        {title}
      </h4>
      {children}
    </section>
  );
}

export function TraceView({
  trace,
  failedTasks = [],
}: {
  trace: Trace;
  /**
   * From the response rather than the trace. It is derivable from the findings,
   * but a run that failed before dispatching has failed tasks and no findings
   * at all, so the two are not interchangeable.
   *
   * Optional because a Q&A run dispatches no enquiries and `QaResponse` has no
   * field for them — not because a brief may leave it out.
   */
  failedTasks?: string[];
}) {
  // One scale across every finding, so the bars compare with each other rather
  // than each row silently using its own axis.
  const scale = Math.max(
    1,
    ...trace.findings.map((finding) => Math.max(finding.hits, finding.neighbours)),
  );

  return (
    <div className="flex flex-col gap-6 rounded-xl border border-line bg-panel px-4 py-5">
      {/*
        Omitted entirely for a run that did no planning. `plan_source` is `""` on
        a Q&A trace, and the alternative — a mode flag, or having `qa_response`
        supply a plan source it does not have — would either duplicate what the
        empty string already says or put a fiction on the wire.
      */}
      {trace.plan_source || trace.plan_rationale ? (
        <div className="flex flex-col gap-1.5">
          {trace.plan_source ? (
            <p className="flex items-center gap-2 text-sm text-ink">
              <Radar
                size={14}
                strokeWidth={1.75}
                aria-hidden="true"
                className="text-faint"
              />
              {PLAN_SOURCE[trace.plan_source] ?? `Plan source: ${trace.plan_source}`}
            </p>
          ) : null}
          {trace.plan_rationale ? (
            <p className="text-xs leading-relaxed text-muted">{trace.plan_rationale}</p>
          ) : null}
        </div>
      ) : null}

      {failedTasks.length ? (
        <p className="rounded-lg border border-warn/40 px-3 py-2 text-xs leading-relaxed text-warn">
          {failedTasks.length === 1
            ? "One enquiry failed"
            : `${formatCount(failedTasks.length)} enquiries failed`}{" "}
          and contributed nothing: {failedTasks.join(", ")}. The brief was written from
          what the rest found.
        </p>
      ) : null}

      {trace.plan.length ? (
        <Block title={`Plan (${formatCount(trace.plan.length)})`}>
          <ul className="flex flex-col gap-2.5">
            {trace.plan.map((task, index) => (
              <li key={`${task.name}-${index}`} className="border-l-2 border-line pl-3">
                <p className="text-sm text-ink">
                  {task.name}
                  {task.is_sweep ? (
                    <span className="ml-2 text-xs text-faint">sweep</span>
                  ) : null}
                </p>
                {task.query.trim() ? (
                  <p className="mt-0.5 text-xs leading-relaxed break-words text-muted">
                    “{task.query}”
                  </p>
                ) : null}
                {task.rationale.trim() ? (
                  <p className="mt-1 text-xs leading-relaxed text-faint">
                    {task.rationale}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </Block>
      ) : null}

      {trace.findings.length ? (
        <Block title={`Findings (${formatCount(trace.findings.length)})`}>
          <div className="flex flex-col gap-2.5">
            <Legend />
            <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-paper">
              {trace.findings.map((finding, index) => (
                <Finding key={`${finding.name}-${index}`} finding={finding} scale={scale} />
              ))}
            </ul>
          </div>
        </Block>
      ) : null}

      <p className="text-xs text-muted">
        {plural(trace.chunks, "chunk")} reached synthesis.
      </p>

      {trace.notes.length ? (
        <Block title="Timeline">
          <Timeline notes={trace.notes} />
        </Block>
      ) : null}
    </div>
  );
}
