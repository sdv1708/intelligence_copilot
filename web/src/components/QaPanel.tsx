import { ChevronRight, Send } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { asApiError, askQuestion } from "../api/client";
import type { ApiError, MaterialOut, QaResponse, Trace } from "../api/client";
import { plural } from "../format";
import type { MeetingTasks } from "../hooks/useMeetingTasks";
import { TraceView } from "./TraceView";
import { Alert, Button, ErrorNote, INPUT, Note } from "./controls";

/**
 * Questions against one meeting's documents.
 *
 * A thread rather than a single answer, because questions about a meeting come
 * in runs — each one narrowing the last, and each answer only worth reading
 * beside the question that produced it. Nothing is persisted: `api/routes/qa.py`
 * writes no rows, so the thread lives exactly as long as the panel is mounted,
 * and the panel says so rather than letting anyone assume otherwise.
 *
 * The state is hand-rolled for the same reason `BriefPanel`'s is — `useRequest`
 * fetches on mount and this is a POST that costs tokens — but the shape differs
 * in the way that matters. `BriefPanel` owns a single slot and needs a ref to
 * decide which response may fill it; here every question owns a slot of its own,
 * so a response is routed by turn id and a slow one cannot land against the
 * wrong question however the requests interleave.
 */

/**
 * One question and whatever came back for it.
 *
 * `question` sits outside the status union because it is the same string in all
 * three states, and it is what a retry re-sends: the composer has been cleared
 * and its text is no longer anywhere else.
 */
type Turn = { id: number; question: string } & (
  | { status: "pending" }
  | { status: "answered"; response: QaResponse }
  /** The request itself failed — a transport error or a non-2xx status. */
  | { status: "failed"; error: ApiError }
);

// --- Citations --------------------------------------------------------------

/** `materialId#cN`, built by `Chunk.source_ref` in `core/schema.py`. */
const SOURCE = /^(.+)#c(\d+)$/;

interface Citation {
  material: string;
  /** The document's filename while it still exists, else the raw material id. */
  label: string;
  chunks: number[];
}

/**
 * Group the flat source refs by the document they came from.
 *
 * An answer routinely cites four chunks of one transcript, and four near
 * identical `material_2025…#c11` labels in a row are unreadable — the filename
 * is the part a person recognises and the chunk numbers are the detail. A ref
 * that does not parse is kept whole rather than dropped: it should not happen,
 * and losing a citation silently is the worse of the two failures.
 */
function citations(sources: string[], filenames: Map<string, string>): Citation[] {
  const grouped = new Map<string, Citation>();

  for (const source of sources) {
    const parsed = SOURCE.exec(source);
    const material = parsed ? parsed[1] : source;
    let citation = grouped.get(material);
    if (!citation) {
      citation = { material, label: filenames.get(material) ?? material, chunks: [] };
      grouped.set(material, citation);
    }
    if (parsed) citation.chunks.push(Number(parsed[2]));
  }

  for (const citation of grouped.values()) {
    citation.chunks.sort((a, b) => a - b);
  }
  return [...grouped.values()];
}

function Sources({
  sources,
  filenames,
}: {
  sources: string[];
  filenames: Map<string, string>;
}) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {citations(sources, filenames).map((citation) => (
        <li
          key={citation.material}
          className="flex max-w-full min-w-0 items-baseline gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-muted"
        >
          <span className="truncate">{citation.label}</span>
          {citation.chunks.length ? (
            <span className="shrink-0 text-faint tabular-nums">
              {citation.chunks.length === 1 ? "chunk" : "chunks"}{" "}
              {citation.chunks.join(", ")}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

// --- One answer -------------------------------------------------------------

/** Why an `ok` answer can still cite nothing, and the two reasons differ. */
const EMPTY_SEARCH =
  "Nothing in this meeting’s documents matched the question, so the model was " +
  "never asked — the answer above is the search coming back empty.";
const NOTHING_CITED =
  "Nothing was cited, so no part of this answer can be traced back to a " +
  "specific passage.";

/**
 * The trace, folded away.
 *
 * Closed by default, unlike the brief's, which is the whole point of generating
 * one. Here the answer is the thing being read and the retrieval behind it is
 * what you open when the answer looks wrong. The disclosure carries no border of
 * its own — `TraceView` brings its own panel — so the summary reads as a link
 * rather than as another box.
 */
function TraceDisclosure({ trace }: { trace: Trace }) {
  return (
    <details className="group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-xs text-muted transition-colors hover:text-ink">
        <ChevronRight
          size={13}
          strokeWidth={2}
          aria-hidden="true"
          className="shrink-0 text-faint transition-transform group-open:rotate-90"
        />
        How this answer was found
      </summary>
      <div className="mt-2.5">
        <TraceView trace={trace} />
      </div>
    </details>
  );
}

function Answer({
  response,
  filenames,
  onRetry,
}: {
  response: QaResponse;
  filenames: Map<string, string>;
  onRetry: () => void;
}) {
  if (!response.ok) {
    return (
      <Alert
        action={
          <Button size="sm" onClick={onRetry}>
            Ask again
          </Button>
        }
      >
        {/*
          `response.answer` is deliberately not rendered. A retrieval failure
          lands on the same node as a legitimately empty search
          (`agents/nodes.py`'s `route_after_qa_retrieval`), so the text on a
          failed run is the "I could not find relevant information" boilerplate
          — and showing it would dress a broken index up as a polite non-answer.
        */}
        {response.error ?? "The question could not be answered, and no reason was given."}
      </Alert>
    );
  }

  /**
   * The search came back with nothing, so the model was never called and the
   * text above is `NO_CONTEXT_ANSWER`. A successful run, but one where saying
   * "answered by" anything would be a fiction.
   */
  const empty = response.trace?.chunks === 0;

  return (
    <div className="flex flex-col gap-3.5">
      {/* The model writes paragraphs and lists; the line breaks are its only
          structure once the text is out of Markdown. */}
      <p className="text-sm leading-relaxed whitespace-pre-line text-ink">
        {response.answer}
      </p>

      <div className="flex flex-col gap-2">
        <p className="text-[11px] font-medium tracking-wide text-faint uppercase">
          {response.sources.length
            ? plural(response.sources.length, "source")
            : "No sources"}
        </p>

        {response.sources.length ? (
          <Sources sources={response.sources} filenames={filenames} />
        ) : (
          <Note>{empty ? EMPTY_SEARCH : NOTHING_CITED}</Note>
        )}
      </div>

      {/*
        The model, when there was one. `qa_response` reports a name either way,
        but the no-context node answers from a constant without calling anything
        (`agents/nodes.py`) — so on a run that retrieved nothing, naming a model
        would credit it with an answer it was never asked for.

        Not `provider`: it is populated here, unlike on a recalled brief, but the
        sidebar already names it and the model is the part that varies.
      */}
      {response.model && !empty ? (
        // `text-muted`, not the `text-faint` used for the label above it: the
        // uppercase labels are the app's de-emphasis pattern, but this is a
        // sentence, and at 12px `text-faint` measures under 4:1 on dark.
        <p className="text-xs text-muted">Answered by {response.model}</p>
      ) : null}

      {response.trace ? <TraceDisclosure trace={response.trace} /> : null}
    </div>
  );
}

function Pending() {
  return (
    <div className="flex flex-col gap-2.5">
      <p role="status" className="text-xs text-muted">
        Searching this meeting&rsquo;s documents and answering&hellip;
      </p>
      <div aria-hidden="true" className="flex flex-col gap-2">
        <span className="h-3 w-full animate-pulse rounded bg-line" />
        <span className="h-3 w-4/5 animate-pulse rounded bg-line" />
      </div>
    </div>
  );
}

function TurnView({
  turn,
  filenames,
  onRetry,
}: {
  turn: Turn;
  filenames: Map<string, string>;
  onRetry: () => void;
}) {
  return (
    <li className="flex flex-col gap-3">
      {/* The question in a panel and the answer as bare prose, rather than two
          opposed bubbles: there are only ever two participants here, and the
          answer is the long one that wants the full column width. */}
      <p className="rounded-xl border border-line bg-panel px-4 py-3 text-sm leading-relaxed whitespace-pre-line text-ink">
        {turn.question}
      </p>

      {turn.status === "pending" ? <Pending /> : null}

      {turn.status === "failed" ? (
        <ErrorNote error={turn.error} onRetry={onRetry} />
      ) : null}

      {turn.status === "answered" ? (
        <Answer response={turn.response} filenames={filenames} onRetry={onRetry} />
      ) : null}
    </li>
  );
}

// --- The panel --------------------------------------------------------------

interface QaPanelProps {
  meetingId: string;
  /** How many documents the meeting has. The API refuses a question without one. */
  documents: number;
  /** Only for naming citations; the panel neither reads nor changes them. */
  materials: MaterialOut[];
  tasks: MeetingTasks;
}

export function QaPanel({ meetingId, documents, materials, tasks }: QaPanelProps) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [asking, setAsking] = useState(false);
  const nextId = useRef(0);
  const end = useRef<HTMLDivElement>(null);
  const fieldId = useId();

  const filenames = useMemo(
    () => new Map(materials.map((material) => [material.id, material.filename])),
    [materials],
  );

  /**
   * Keep the composer in view as the thread grows.
   *
   * A new turn is inserted directly above the composer, which pushes it below
   * the fold — and the composer is where the cursor is and where the answer
   * appears. Keyed on the count rather than on `turns`, so a response landing in
   * an existing turn does not yank the page while its trace is being read.
   */
  useEffect(() => {
    if (turns.length) end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns.length]);

  /**
   * Ask, either for the first time or again.
   *
   * `existing` is the id of a turn being retried, which is replaced in place
   * rather than appended: a retry is the same question, and letting it stack up
   * a second copy would make the thread a record of the network instead of a
   * record of the conversation.
   */
  async function ask(asked: string, existing?: number) {
    const id = existing ?? (nextId.current += 1);
    const pending: Turn = { id, question: asked, status: "pending" };
    setTurns((current) =>
      existing === undefined
        ? [...current, pending]
        : current.map((turn) => (turn.id === id ? pending : turn)),
    );
    setAsking(true);

    // Routed by id rather than into a single slot, so nothing here depends on
    // which request finishes first.
    const settle = (turn: Turn) =>
      setTurns((current) => current.map((each) => (each.id === id ? turn : each)));

    try {
      // Through `tasks.run` because `api/routes/qa.py` takes the same
      // per-meeting lock a brief does — `Retriever.recall` backfills the index,
      // so an upload arriving mid-question would block invisibly.
      const response = await tasks.run(meetingId, () => askQuestion(meetingId, asked));
      settle({ id, question: asked, status: "answered", response });
    } catch (cause) {
      settle({ id, question: asked, status: "failed", error: asApiError(cause) });
    } finally {
      setAsking(false);
    }
  }

  function submit() {
    const asked = question.trim();
    if (!asked) return;
    setQuestion("");
    void ask(asked);
  }

  const busy = tasks.isBusy(meetingId);
  const blocked = documents === 0;

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-sm font-medium text-ink">Questions</h2>

      {blocked ? (
        <Note>
          Questions are answered from the meeting&rsquo;s documents. Add at least
          one above.
        </Note>
      ) : null}

      {turns.length ? (
        <ol className="flex flex-col gap-7">
          {turns.map((turn) => (
            <TurnView
              key={turn.id}
              turn={turn}
              filenames={filenames}
              onRetry={() => void ask(turn.question, turn.id)}
            />
          ))}
        </ol>
      ) : blocked ? null : (
        <p className="rounded-xl border border-line bg-panel px-4 py-6 text-sm leading-relaxed text-muted">
          Ask about anything in this meeting&rsquo;s documents and the answer
          comes back with the passages it was drawn from. Nothing here is saved —
          the thread is gone once you leave this meeting.
        </p>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        className="flex flex-col gap-2"
      >
        <label htmlFor={fieldId} className="sr-only">
          Ask a question about this meeting
        </label>
        <textarea
          id={fieldId}
          rows={3}
          value={question}
          disabled={blocked}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends and Shift+Enter breaks the line, which is what every
            // composer does — and a question long enough to need two lines is
            // exactly the one worth being able to write.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder="What was decided, and who owns it?"
          className={`${INPUT} resize-y`}
        />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <p className="mr-auto text-xs text-muted">
            Enter to ask, Shift+Enter for a new line.
          </p>
          <Button
            type="submit"
            variant="primary"
            busy={asking}
            // `busy` covers this meeting's other writes as well as this one:
            // the server would serialise them behind its lock and the request
            // would look like a hang.
            disabled={busy || blocked || !question.trim()}
          >
            <Send size={14} strokeWidth={1.75} aria-hidden="true" />
            Ask
          </Button>
        </div>
      </form>

      <div ref={end} aria-hidden="true" />
    </section>
  );
}
