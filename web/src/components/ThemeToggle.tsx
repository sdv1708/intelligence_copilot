import { Monitor, Moon, Sun } from "lucide-react";

import type { Theme, ThemePreference } from "../hooks/useTheme";

const ICONS = { system: Monitor, light: Sun, dark: Moon } as const;

const NEXT: Record<ThemePreference, ThemePreference> = {
  system: "light",
  light: "dark",
  dark: "system",
};

const NAMES: Record<ThemePreference, string> = {
  system: "system theme",
  light: "light theme",
  dark: "dark theme",
};

/**
 * One button rather than three. The label says what pressing it will do, so the
 * control is legible without a tooltip and readable by a screen reader.
 */
export function ThemeToggle({ theme }: { theme: Theme }) {
  const Icon = ICONS[theme.preference];
  const next = NEXT[theme.preference];

  return (
    <button
      type="button"
      onClick={theme.cycle}
      title={`Using ${NAMES[theme.preference]}. Switch to ${NAMES[next]}.`}
      aria-label={`Switch to ${NAMES[next]}`}
      className="flex size-8 shrink-0 items-center justify-center rounded-md text-muted transition-colors hover:bg-line hover:text-ink"
    >
      <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}
