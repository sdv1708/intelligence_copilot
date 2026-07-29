import { PanelLeft } from "lucide-react";
import { useEffect, useState } from "react";

import { getHealth } from "./api/client";
import { Sidebar } from "./components/Sidebar";
import { StatusPanel } from "./components/StatusPanel";
import { useRequest } from "./hooks/useRequest";
import { useTheme } from "./hooks/useTheme";
import { signalFor } from "./status";

const RAIL = "w-[17rem]";

export function App() {
  const theme = useTheme();
  const { state, reload } = useRequest((options) => getHealth(options));
  const signal = signalFor(state);

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

  return (
    <div className="flex h-dvh overflow-hidden bg-paper text-ink">
      <aside
        className={`hidden shrink-0 border-r border-line md:block ${RAIL}`}
      >
        <Sidebar
          signal={signal}
          theme={theme}
          onClose={() => setRailOpen(false)}
        />
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
            <Sidebar
              signal={signal}
              theme={theme}
              onClose={() => setRailOpen(false)}
            />
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
            <StatusPanel state={state} signal={signal} onRetry={reload} />
          </div>
        </main>
      </div>
    </div>
  );
}
