import { PanelLeftClose, ScrollText } from "lucide-react";

import type { MeetingOut } from "../api/client";
import type { RequestState } from "../hooks/useRequest";
import type { Theme } from "../hooks/useTheme";
import type { Signal } from "../status";
import { HealthLine } from "./HealthLine";
import { MeetingList } from "./MeetingList";
import { ThemeToggle } from "./ThemeToggle";

interface SidebarProps {
  signal: Signal;
  theme: Theme;
  meetings: RequestState<MeetingOut[]>;
  selectedId: string | null;
  composing: boolean;
  /** True while the status view is the one on screen. */
  showingStatus: boolean;
  isBusy: (meetingId: string) => boolean;
  onSelect: (meetingId: string) => void;
  onNew: () => void;
  onStatus: () => void;
  onReloadMeetings: () => void;
  /** Only rendered below the layout's breakpoint, where the rail overlays. */
  onClose: () => void;
}

export function Sidebar({
  signal,
  theme,
  meetings,
  selectedId,
  composing,
  showingStatus,
  isBusy,
  onSelect,
  onNew,
  onStatus,
  onReloadMeetings,
  onClose,
}: SidebarProps) {
  return (
    <div className="flex h-full flex-col bg-rail">
      <header className="flex h-14 shrink-0 items-center gap-2 px-3">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-accent text-paper">
          <ScrollText size={15} strokeWidth={1.75} aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium tracking-tight text-ink">
          Intelligence Copilot
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Hide the sidebar"
          className="flex size-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-line hover:text-ink md:hidden"
        >
          <PanelLeftClose size={16} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </header>

      <MeetingList
        state={meetings}
        selectedId={selectedId}
        composing={composing}
        isBusy={isBusy}
        onSelect={onSelect}
        onNew={onNew}
        onRetry={onReloadMeetings}
      />

      <footer className="flex shrink-0 items-center gap-2 border-t border-line px-3 py-2.5">
        {/*
          The health reading is the way into the status view rather than a
          separate nav item: the only reason to open that screen is the reading
          itself, so the reading is what you click.
        */}
        <button
          type="button"
          onClick={onStatus}
          aria-current={showingStatus ? "page" : undefined}
          className={`min-w-0 flex-1 rounded-md px-1.5 py-1 text-left transition-colors ${
            showingStatus ? "bg-line" : "hover:bg-line"
          }`}
        >
          <HealthLine signal={signal} />
        </button>
        <ThemeToggle theme={theme} />
      </footer>
    </div>
  );
}
