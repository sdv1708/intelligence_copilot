import { ChevronRight } from "lucide-react";

import type {
  ActionItem,
  ActionItemStatus,
  MeetingBrief,
} from "../api/client";
import { formatCount, plural } from "../format";

/**
 * The brief as a document rather than a dashboard.
 *
 * Everything about the layout here is calibrated against what the model
 * actually writes into `data/briefs.db`, not against the field names: a
 * "key topic" is a three-line paragraph, an agenda "topic" carries its own
 * "Outcome: ..." clause, and one real brief carries seventeen citations. So
 * topics are a prose list and not chips, and the evidence is behind a
 * disclosure rather than dumped under the agenda.
 */

/**
 * Status is the one place a colour carries meaning, so it never travels alone:
 * the word is always rendered beside it.
 */
const STATUS: Record<ActionItemStatus, string> = {
  open: "border-line-strong text-muted",
  blocked: "border-crit/45 text-crit",
  done: "border-ok/45 text-ok",
};

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2.5">
      <h3 className="text-[11px] font-medium tracking-wide text-faint uppercase">
        {title}
      </h3>
      {children}
    </section>
  );
}

function ActionRow({ item }: { item: ActionItem }) {
  return (
    <li className="flex flex-col gap-1.5 px-4 py-3">
      <p className="text-sm leading-relaxed text-ink">{item.item}</p>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <span
          className={`rounded-full border px-2 py-0.5 ${STATUS[item.status] ?? STATUS.open}`}
        >
          {item.status}
        </span>
        {/* Real rows hold "TBD" as an owner; it is still what was written. */}
        <span>{item.owner.trim() || "No owner"}</span>
        {item.due ? <span>· due {item.due}</span> : null}
      </div>
    </li>
  );
}

function Agenda({ brief }: { brief: MeetingBrief }) {
  const total = brief.proposed_agenda.reduce((sum, item) => sum + item.minutes, 0);

  return (
    <div className="flex flex-col gap-2">
      <ol className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-panel">
        {brief.proposed_agenda.map((item, index) => (
          <li key={`${item.topic}-${index}`} className="flex gap-3 px-4 py-3">
            {/* Tabular so the minute column stays a column however wide the
                numbers get. */}
            <span className="w-14 shrink-0 pt-px text-right text-xs text-muted tabular-nums">
              {item.minutes} min
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm leading-relaxed text-ink">{item.topic}</p>
              {item.owner?.trim() ? (
                <p className="mt-1 text-xs text-muted">{item.owner}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
      <p className="text-xs text-muted">
        {total} minutes over {plural(brief.proposed_agenda.length, "item")}.
      </p>
    </div>
  );
}

function Evidence({ brief }: { brief: MeetingBrief }) {
  return (
    <details className="group overflow-hidden rounded-xl border border-line bg-panel">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm text-ink">
        <ChevronRight
          size={14}
          strokeWidth={2}
          aria-hidden="true"
          className="shrink-0 text-faint transition-transform group-open:rotate-90"
        />
        {plural(brief.evidence.length, "citation")}
      </summary>
      <ol className="divide-y divide-line border-t border-line">
        {brief.evidence.map((entry, index) => (
          <li key={`${entry.source}-${index}`} className="flex flex-col gap-1.5 px-4 py-3">
            <code className="text-[11px] break-all text-faint">
              {entry.source}
              {/* Null on every row in the real database — the label already
                  carries the chunk number, so it is only shown when it adds
                  something the label does not. */}
              {entry.chunk_id === null ? "" : ` · chunk ${entry.chunk_id}`}
            </code>
            {/* Snippets keep the source document's line breaks, and those are
                often the only structure a slide deck's text has left. */}
            <p className="text-sm leading-relaxed whitespace-pre-line text-muted">
              {entry.snippet}
            </p>
          </li>
        ))}
      </ol>
    </details>
  );
}

/**
 * An empty section is information: a brief with no action items means the
 * model found none, and a blank space says that ambiguously. Every section
 * that can be empty says so in words instead of disappearing — except the
 * evidence, whose absence is already visible as a missing disclosure.
 */
function Empty({ children }: { children: string }) {
  return <p className="text-sm leading-relaxed text-muted">{children}</p>;
}

export function BriefDocument({ brief }: { brief: MeetingBrief }) {
  return (
    <article className="flex flex-col gap-7">
      {brief.time_window ? (
        <p className="text-xs text-muted">Covering {brief.time_window}</p>
      ) : null}

      <Section title="Recap">
        {brief.last_meeting_recap.trim() ? (
          <p className="text-sm leading-relaxed whitespace-pre-line text-ink">
            {brief.last_meeting_recap}
          </p>
        ) : (
          <Empty>No previous meeting was found to recap.</Empty>
        )}
      </Section>

      <Section title={`Open action items (${formatCount(brief.open_action_items.length)})`}>
        {brief.open_action_items.length ? (
          <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-panel">
            {brief.open_action_items.map((item, index) => (
              <ActionRow key={`${item.item}-${index}`} item={item} />
            ))}
          </ul>
        ) : (
          <Empty>Nothing outstanding was found in the documents.</Empty>
        )}
      </Section>

      <Section title="Key topics">
        {brief.key_topics_today.length ? (
          <ul className="flex flex-col gap-2.5">
            {brief.key_topics_today.map((topic, index) => (
              <li
                key={`${topic}-${index}`}
                className="border-l-2 border-line pl-3 text-sm leading-relaxed text-ink"
              >
                {topic}
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No topics were proposed.</Empty>
        )}
      </Section>

      <Section title="Proposed agenda">
        {brief.proposed_agenda.length ? (
          <Agenda brief={brief} />
        ) : (
          <Empty>No agenda was proposed.</Empty>
        )}
      </Section>

      {brief.evidence.length ? (
        <Section title="Evidence">
          <Evidence brief={brief} />
        </Section>
      ) : (
        <Section title="Evidence">
          <Empty>
            Nothing was cited. A brief with no evidence was written from the
            model&rsquo;s own reading rather than from retrieved text.
          </Empty>
        </Section>
      )}
    </article>
  );
}
