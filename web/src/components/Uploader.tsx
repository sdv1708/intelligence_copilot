import { Check, Upload, X } from "lucide-react";
import { useRef, useState } from "react";

import { asApiError, pasteMaterial, uploadMaterials } from "../api/client";
import type { ApiError, IngestOutcome } from "../api/client";
import { formatCount, plural } from "../format";
import type { MeetingTasks } from "../hooks/useMeetingTasks";
import { Button, ErrorNote, Field, INPUT } from "./controls";

/** What the parsers in `core/parsing.py` dispatch on. Anything else reads empty. */
const ACCEPT = ".pdf,.docx,.pptx,.txt";

interface DropzoneProps {
  disabled: boolean;
  onFiles: (files: File[]) => void;
}

function Dropzone({ disabled, onFiles }: DropzoneProps) {
  const input = useRef<HTMLInputElement>(null);
  // Dragging over a child fires `dragleave` on the parent, so a boolean flickers
  // the highlight off the moment the pointer crosses the icon. Counting the
  // enter/leave pairs is what keeps it steady.
  const depth = useRef(0);
  const [over, setOver] = useState(false);

  function reset() {
    depth.current = 0;
    setOver(false);
  }

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          if (disabled) return;
          depth.current += 1;
          setOver(true);
        }}
        onDragOver={(event) => {
          // Without this the browser navigates to the file instead of dropping.
          event.preventDefault();
          if (!disabled) event.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          depth.current -= 1;
          if (depth.current <= 0) reset();
        }}
        onDrop={(event) => {
          event.preventDefault();
          reset();
          if (disabled) return;
          const files = Array.from(event.dataTransfer.files);
          if (files.length) onFiles(files);
        }}
        className={`flex w-full flex-col items-center gap-1.5 rounded-xl border border-dashed px-4 py-8 transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
          over
            ? "border-accent bg-accent-soft"
            : "border-line-strong hover:border-accent hover:bg-panel"
        }`}
      >
        <Upload
          size={18}
          strokeWidth={1.75}
          aria-hidden="true"
          className={over ? "text-accent-ink" : "text-muted"}
        />
        <span className="text-sm font-medium text-ink">
          Drop files here, or click to browse
        </span>
        <span className="text-xs text-faint">
          PDF, DOCX, PPTX or TXT · up to 25 MB each
        </span>
      </button>

      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          // Clearing the value is what lets the same file be picked twice in a
          // row — otherwise the second `change` never fires.
          event.target.value = "";
          if (files.length) onFiles(files);
        }}
      />
    </>
  );
}

function OutcomeRow({ outcome }: { outcome: IngestOutcome }) {
  const Icon = outcome.success ? Check : X;
  return (
    <li className="flex items-start gap-2.5 px-4 py-2.5">
      <Icon
        size={15}
        strokeWidth={2}
        aria-hidden="true"
        className={`mt-0.5 shrink-0 ${outcome.success ? "text-ok" : "text-crit"}`}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-ink">{outcome.filename}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-muted">
          {outcome.success
            ? `${plural(outcome.chunks, "chunk")} from ${formatCount(
                outcome.characters,
              )} characters`
            : (outcome.error ?? "Ingestion failed for an unstated reason.")}
        </p>
      </div>
    </li>
  );
}

/**
 * The per-file outcomes of the last ingestion.
 *
 * `POST .../materials` answers 200 with `ingested` and `failed` both possibly
 * non-zero — a corrupt PDF alongside three good decks costs you the PDF and
 * nothing else. Rendering only the status code would lose the failures
 * entirely, which is exactly the class of silent loss this overhaul exists to
 * fix, so every file gets a line whether it worked or not.
 */
function Report({
  outcomes,
  onDismiss,
}: {
  outcomes: IngestOutcome[];
  onDismiss: () => void;
}) {
  const failed = outcomes.filter((outcome) => !outcome.success).length;
  const ingested = outcomes.length - failed;

  return (
    <section className="overflow-hidden rounded-xl border border-line bg-panel">
      <header className="flex items-center gap-3 border-b border-line px-4 py-2.5">
        <h3 className="min-w-0 flex-1 text-sm font-medium text-ink">
          {failed === 0
            ? `Added ${plural(ingested, "file")}`
            : `Added ${ingested} of ${plural(outcomes.length, "file")}`}
        </h3>
        <Button size="sm" variant="ghost" onClick={onDismiss}>
          Dismiss
        </Button>
      </header>
      <ul className="divide-y divide-line">
        {outcomes.map((outcome, index) => (
          <OutcomeRow key={`${outcome.filename}-${index}`} outcome={outcome} />
        ))}
      </ul>
    </section>
  );
}

interface UploaderProps {
  meetingId: string;
  /** True while this meeting holds the server's lock for something else. */
  busy: boolean;
  run: MeetingTasks["run"];
  /** Called after any ingestion, successful or not, to refresh the list. */
  onIngested: () => void;
}

export function Uploader({ meetingId, busy, run, onIngested }: UploaderProps) {
  const [outcomes, setOutcomes] = useState<IngestOutcome[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("");

  async function ingest(task: () => Promise<IngestOutcome[]>) {
    setError(null);
    setOutcomes(null);
    try {
      setOutcomes(await run(meetingId, task));
    } catch (cause) {
      setError(asApiError(cause));
    } finally {
      // Even a batch where everything failed can have changed the meeting: a
      // file that stored and then produced no chunks leaves a material behind.
      onIngested();
    }
  }

  function upload(files: File[]) {
    void ingest(async () => {
      const response = await uploadMaterials(meetingId, files);
      return response.results;
    });
  }

  function paste() {
    const body = text.trim();
    if (!body) return;
    void ingest(async () => {
      const outcome = await pasteMaterial(
        meetingId,
        body,
        filename.trim() || undefined,
      );
      setText("");
      setFilename("");
      setPasting(false);
      return [outcome];
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <Dropzone disabled={busy} onFiles={upload} />

      {pasting ? (
        <div className="flex flex-col gap-4 rounded-xl border border-line bg-panel px-4 py-4">
          <Field id="paste-text" label="Text">
            <textarea
              id="paste-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={7}
              disabled={busy}
              autoFocus
              placeholder="Paste a transcript, notes, or an email thread."
              className={`${INPUT} resize-y font-mono text-[13px]`}
            />
          </Field>

          <Field
            id="paste-name"
            label="Name"
            hint="Optional. Used as the material's filename; defaults to pasted_text.txt."
          >
            <input
              id="paste-name"
              value={filename}
              onChange={(event) => setFilename(event.target.value)}
              maxLength={255}
              disabled={busy}
              placeholder="pasted_text.txt"
              className={INPUT}
            />
          </Field>

          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              onClick={paste}
              busy={busy}
              disabled={!text.trim()}
            >
              Add text
            </Button>
            <Button onClick={() => setPasting(false)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button size="sm" variant="ghost" onClick={() => setPasting(true)} disabled={busy}>
            Paste text instead
          </Button>
        </div>
      )}

      {error ? <ErrorNote error={error} /> : null}
      {outcomes ? (
        <Report outcomes={outcomes} onDismiss={() => setOutcomes(null)} />
      ) : null}
    </div>
  );
}
