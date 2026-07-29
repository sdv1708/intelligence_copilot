import { Loader2 } from "lucide-react";
import { useCallback, useState } from "react";

import { ApiError, deleteMeeting, getMeeting, listMaterials } from "../api/client";
import type { MeetingOut } from "../api/client";
import { meetingTitle, plural } from "../format";
import type { MeetingTasks } from "../hooks/useMeetingTasks";
import { useRequest } from "../hooks/useRequest";
import { MaterialsList } from "./MaterialsList";
import { Uploader } from "./Uploader";
import { Button, ErrorNote } from "./controls";

interface MeetingPanelProps {
  meetingId: string;
  tasks: MeetingTasks;
  /** The counts the sidebar shows have changed. */
  onChanged: () => void;
  /** The meeting is gone; nothing here can be shown any more. */
  onDeleted: () => void;
}

/**
 * What deleting a meeting takes with it, naming only what is actually there.
 * "its 0 briefs" is noise in a sentence whose job is to be read carefully.
 */
function losses(documents: number, briefs: number): string {
  const parts = [];
  if (documents) parts.push(`its ${plural(documents, "document")}`);
  if (briefs) parts.push(`its ${plural(briefs, "brief")}`);
  return parts.length ? `, ${parts.join(", ")},` : "";
}

function Chip({ children }: { children: string }) {
  return (
    <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">
      {children}
    </span>
  );
}

function Heading({
  meeting,
  documents,
  busy,
  onDelete,
}: {
  meeting: MeetingOut;
  /** Counted from the live materials list, not the meeting's own stale count. */
  documents: number;
  busy: boolean;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <h1 className="min-w-0 flex-1 text-2xl font-semibold tracking-tight text-ink">
          {meetingTitle(meeting.title)}
        </h1>

        {confirming ? (
          <div className="flex shrink-0 items-center gap-1.5">
            <Button size="sm" variant="danger" onClick={onDelete} disabled={busy}>
              Delete everything
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setConfirming(true)}
            disabled={busy}
          >
            Delete meeting
          </Button>
        )}
      </div>

      {confirming ? (
        <p className="text-sm leading-relaxed text-crit">
          This removes the meeting{losses(documents, meeting.brief_count)} and its
          search index. It cannot be undone.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm text-muted">
        {meeting.date ? <span>{meeting.date}</span> : null}
        {meeting.date && meeting.attendees.length ? <span>·</span> : null}
        {meeting.attendees.length ? (
          <span className="min-w-0">{meeting.attendees.join(", ")}</span>
        ) : null}
      </div>

      {meeting.tags.length ? (
        <div className="flex flex-wrap gap-1.5">
          {meeting.tags.map((tag) => (
            <Chip key={tag}>{tag}</Chip>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-4" aria-hidden="true">
      <span className="h-7 w-64 animate-pulse rounded bg-line" />
      <span className="h-3 w-40 animate-pulse rounded bg-line" />
      <span className="mt-4 h-28 w-full animate-pulse rounded-xl bg-line" />
    </div>
  );
}

export function MeetingPanel({
  meetingId,
  tasks,
  onChanged,
  onDeleted,
}: MeetingPanelProps) {
  const meeting = useRequest(
    (options) => getMeeting(meetingId, options),
    [meetingId],
  );
  const materials = useRequest(
    (options) => listMaterials(meetingId, options),
    [meetingId],
  );
  const [deleteError, setDeleteError] = useState<ApiError | null>(null);

  const busy = tasks.isBusy(meetingId);

  /**
   * Refetch what an ingestion or deletion changed.
   *
   * Deliberately *not* `meeting.reload()` as well. `useRequest` drops back to
   * `loading` while it refetches, and this component renders a skeleton in
   * that state — so reloading the meeting here would unmount the uploader and
   * throw away the per-file report the user is reading. Nothing in this phase
   * edits the meeting record itself; only its document list moves, so only
   * that is refetched, and the sidebar's counts come from `onChanged`.
   */
  const reloadMaterials = materials.reload;
  const refresh = useCallback(() => {
    reloadMaterials();
    onChanged();
  }, [reloadMaterials, onChanged]);

  async function removeMeeting() {
    setDeleteError(null);
    try {
      await tasks.run(meetingId, () => deleteMeeting(meetingId));
      onDeleted();
    } catch (cause) {
      setDeleteError(
        cause instanceof ApiError
          ? cause
          : new ApiError({
              message: cause instanceof Error ? cause.message : String(cause),
              status: 0,
              url: "",
            }),
      );
    }
  }

  if (meeting.state.status === "loading") return <Skeleton />;

  if (meeting.state.status === "failed") {
    const error = meeting.state.error;
    return (
      <div className="flex flex-col gap-4">
        {/* `ErrorNote` withholds the retry itself for the kinds retrying
            cannot fix, so there is no condition to duplicate here. */}
        <ErrorNote error={error} onRetry={meeting.reload} />
        {error.kind === "MeetingNotFoundError" ? (
          <Button onClick={onDeleted}>Back to status</Button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <Heading
        meeting={meeting.state.data}
        documents={
          materials.state.status === "ready"
            ? materials.state.data.length
            : meeting.state.data.material_count
        }
        busy={busy}
        onDelete={() => void removeMeeting()}
      />

      {deleteError ? <ErrorNote error={deleteError} /> : null}

      <section className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-ink">Documents</h2>
          {busy ? (
            <span className="flex items-center gap-1.5 text-xs text-muted">
              <Loader2
                size={12}
                strokeWidth={1.75}
                aria-hidden="true"
                className="animate-spin"
              />
              Working — this meeting is locked until it finishes
            </span>
          ) : null}
        </div>

        {/*
          Keyed on the meeting so switching selection clears the last upload's
          report rather than showing it against a different meeting's documents.
        */}
        <Uploader
          key={meetingId}
          meetingId={meetingId}
          busy={busy}
          run={tasks.run}
          onIngested={refresh}
        />

        {materials.state.status === "loading" ? (
          <div
            aria-hidden="true"
            className="h-16 w-full animate-pulse rounded-xl bg-line"
          />
        ) : null}

        {materials.state.status === "failed" ? (
          <ErrorNote error={materials.state.error} onRetry={materials.reload} />
        ) : null}

        {materials.state.status === "ready" ? (
          <MaterialsList
            meetingId={meetingId}
            materials={materials.state.data}
            busy={busy}
            run={tasks.run}
            onDeleted={refresh}
          />
        ) : null}
      </section>
    </div>
  );
}
