import { Loader2, Plus, RotateCw } from "lucide-react";

import type { MeetingOut } from "../api/client";
import { meetingSummary, meetingTitle } from "../format";
import type { RequestState } from "../hooks/useRequest";
import { Button } from "./controls";

interface MeetingListProps {
  state: RequestState<MeetingOut[]>;
  /** The meeting currently shown in the main column, if any. */
  selectedId: string | null;
  /** True while the composer is open, so nothing in the list reads as current. */
  composing: boolean;
  isBusy: (meetingId: string) => boolean;
  onSelect: (meetingId: string) => void;
  onNew: () => void;
  onRetry: () => void;
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-1 px-1" aria-hidden="true">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex flex-col gap-1.5 py-2">
          <span className="h-3 w-32 animate-pulse rounded bg-line" />
          <span className="h-2.5 w-20 animate-pulse rounded bg-line" />
        </div>
      ))}
    </div>
  );
}

export function MeetingList({
  state,
  selectedId,
  composing,
  isBusy,
  onSelect,
  onNew,
  onRetry,
}: MeetingListProps) {
  return (
    <>
      <div className="px-3 pb-2">
        <Button
          variant="secondary"
          onClick={onNew}
          aria-current={composing ? "page" : undefined}
          className={`w-full ${composing ? "bg-panel" : ""}`}
        >
          <Plus size={15} strokeWidth={1.75} aria-hidden="true" />
          New meeting
        </Button>
      </div>

      <nav
        aria-label="Meetings"
        className="min-h-0 flex-1 overflow-y-auto px-3 pb-3"
      >
        <h2 className="px-1 pb-1.5 text-[11px] font-medium tracking-wide text-faint uppercase">
          Meetings
        </h2>

        {state.status === "loading" ? <Skeleton /> : null}

        {state.status === "failed" ? (
          <div className="flex flex-col items-start gap-2 px-1 py-2">
            <p className="text-xs leading-relaxed text-muted">
              The meeting list could not be loaded.
            </p>
            <Button size="sm" onClick={onRetry}>
              <RotateCw size={13} strokeWidth={1.75} aria-hidden="true" />
              Retry
            </Button>
          </div>
        ) : null}

        {state.status === "ready" && state.data.length === 0 ? (
          <p className="px-1 py-2 text-xs leading-relaxed text-muted">
            No meetings yet. Create one, then add the documents it should be
            briefed from.
          </p>
        ) : null}

        {state.status === "ready" && state.data.length > 0 ? (
          <ul className="flex flex-col gap-0.5">
            {state.data.map((meeting) => {
              const selected = meeting.id === selectedId;
              const busy = isBusy(meeting.id);
              return (
                <li key={meeting.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(meeting.id)}
                    aria-current={selected ? "page" : undefined}
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors ${
                      selected
                        ? "bg-accent-soft text-accent-ink"
                        : "text-ink hover:bg-line"
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm">
                        {meetingTitle(meeting.title)}
                      </span>
                      <span
                        className={`block truncate text-[11px] ${
                          selected ? "text-accent-ink/75" : "text-faint"
                        }`}
                      >
                        {meeting.date ? `${meeting.date} · ` : ""}
                        {meetingSummary(meeting.material_count, meeting.brief_count)}
                      </span>
                    </span>
                    {busy ? (
                      <Loader2
                        size={13}
                        strokeWidth={1.75}
                        aria-label="Working"
                        className="shrink-0 animate-spin text-muted"
                      />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
      </nav>
    </>
  );
}
