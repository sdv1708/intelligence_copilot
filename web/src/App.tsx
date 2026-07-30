import { PanelLeft } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { getHealth, listMeetings } from "./api/client";
import { MeetingPanel } from "./components/MeetingPanel";
import { NewMeeting } from "./components/NewMeeting";
import { Sidebar } from "./components/Sidebar";
import { StatusPanel } from "./components/StatusPanel";
import { useMeetingTasks } from "./hooks/useMeetingTasks";
import { useRequest } from "./hooks/useRequest";
import { useTheme } from "./hooks/useTheme";
import { signalFor } from "./status";

const RAIL = "w-[17rem]";

/**
 * What the main column shows. A union rather than a nullable meeting id, so
 * "no meeting selected" and "composing a new one" cannot be the same state.
 */
type View =
  | { kind: "status" }
  | { kind: "new" }
  | { kind: "meeting"; id: string };

export function App() {
  const theme = useTheme();
  const health = useRequest((options) => getHealth(options));
  const meetings = useRequest((options) => listMeetings(options));
  const signal = signalFor(health.state);
  const tasks = useMeetingTasks();

  const [view, setView] = useState<View>({ kind: "status" });

  // Only used below the breakpoint, where the rail overlays rather than sits
  // beside the content.
  const [railOpen, setRailOpen] = useState(false);

  useEffect(() => {
    if (!railOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setRailOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [railOpen]);

  // Every navigation closes the overlay rail: on a phone the sidebar covers
  // what was just chosen, so leaving it open hides the result of the click.
  const go = useCallback((next: View) => {
    setView(next);
    setRailOpen(false);
  }, []);

  const reloadMeetings = meetings.reload;

  const sidebar = (
    <Sidebar
      signal={signal}
      theme={theme}
      meetings={meetings.state}
      selectedId={view.kind === "meeting" ? view.id : null}
      composing={view.kind === "new"}
      showingStatus={view.kind === "status"}
      isBusy={tasks.isBusy}
      onSelect={(id) => go({ kind: "meeting", id })}
      onNew={() => go({ kind: "new" })}
      onStatus={() => go({ kind: "status" })}
      onReloadMeetings={reloadMeetings}
      onClose={() => setRailOpen(false)}
    />
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-paper text-ink">
      <aside className={`hidden shrink-0 border-r border-line md:block ${RAIL}`}>
        {sidebar}
      </aside>

      {railOpen ? (
        <>
          <button
            type="button"
            aria-label="Hide the sidebar"
            onClick={() => setRailOpen(false)}
            className="fixed inset-0 z-30 bg-black/40 md:hidden"
          />
          <aside
            className={`fixed inset-y-0 left-0 z-40 border-r border-line md:hidden ${RAIL}`}
          >
            {sidebar}
          </aside>
        </>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 md:hidden">
          <button
            type="button"
            onClick={() => setRailOpen(true)}
            aria-label="Show the sidebar"
            className="flex size-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-rail hover:text-ink"
          >
            <PanelLeft size={16} strokeWidth={1.75} aria-hidden="true" />
          </button>
          <span className="truncate text-sm font-medium tracking-tight">
            Intelligence Copilot
          </span>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-column px-5 py-10 md:px-8 md:py-14">
            {view.kind === "status" ? (
              <StatusPanel
                state={health.state}
                signal={signal}
                onRetry={health.reload}
              />
            ) : null}

            {view.kind === "new" ? (
              <NewMeeting
                onCreated={(meeting) => {
                  reloadMeetings();
                  go({ kind: "meeting", id: meeting.id });
                }}
                onCancel={() => go({ kind: "status" })}
              />
            ) : null}

            {view.kind === "meeting" ? (
              // Keyed so switching meetings remounts rather than carrying the
              // previous one's transient state — confirmations, upload reports
              // — across to a different meeting's documents.
              <MeetingPanel
                key={view.id}
                meetingId={view.id}
                tasks={tasks}
                onChanged={reloadMeetings}
                onDeleted={() => {
                  reloadMeetings();
                  go({ kind: "status" });
                }}
              />
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
}
