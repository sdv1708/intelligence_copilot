import { PanelLeftClose, ScrollText } from "lucide-react";

import type { Theme } from "../hooks/useTheme";
import type { Signal } from "../status";
import { HealthLine } from "./HealthLine";
import { ThemeToggle } from "./ThemeToggle";

interface SidebarProps {
  signal: Signal;
  theme: Theme;
  /** Only rendered below the layout's breakpoint, where the rail overlays. */
  onClose: () => void;
}

export function Sidebar({ signal, theme, onClose }: SidebarProps) {
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

      <nav
        aria-label="Meetings"
        className="min-h-0 flex-1 overflow-y-auto px-3 pb-3"
      >
        <h2 className="px-1 pb-2 text-[11px] font-medium tracking-wide text-faint uppercase">
          Meetings
        </h2>

        {/*
          A build-state note, not an empty state: the database this talks to
          already holds meetings. The list, the create form and selection are
          the next slice of work, and this block goes when they land.
        */}
        <p className="rounded-md border border-dashed border-line-strong px-3 py-4 text-xs leading-relaxed text-muted">
          The meeting list is not wired up yet. This build is the shell — layout,
          theming, the status line and the API client.
        </p>
      </nav>

      <footer className="flex shrink-0 items-center gap-2 border-t border-line px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <HealthLine signal={signal} />
        </div>
        <ThemeToggle theme={theme} />
      </footer>
    </div>
  );
}
