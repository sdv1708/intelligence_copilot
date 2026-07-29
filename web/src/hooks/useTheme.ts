import { useCallback, useEffect, useState } from "react";

/**
 * Three states, not two. "System" has to be a real choice a user can return to,
 * or picking dark once means never following the OS again.
 */
export type ThemePreference = "system" | "light" | "dark";

/** Must match the inline script in `index.html`, which runs before React does. */
const STORAGE_KEY = "copilot-theme";

const ORDER: ThemePreference[] = ["system", "light", "dark"];

function readStored(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" || value === "system"
      ? value
      : "system";
  } catch {
    // Storage can be blocked entirely; following the OS is the right default.
    return "system";
  }
}

function prefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export interface Theme {
  preference: ThemePreference;
  /** What is actually on screen once "system" has been resolved. */
  resolved: "light" | "dark";
  setPreference: (next: ThemePreference) => void;
  /** Advances system → light → dark → system, for a single-button control. */
  cycle: () => void;
}

export function useTheme(): Theme {
  const [preference, setPreference] = useState<ThemePreference>(readStored);
  const [systemDark, setSystemDark] = useState(prefersDark);

  // Only meaningful while the preference is "system", but the listener is
  // cheap and keeping it unconditional avoids a stale reading on the way back.
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const resolved: "light" | "dark" =
    preference === "system" ? (systemDark ? "dark" : "light") : preference;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolved === "dark");
    try {
      localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      // Nothing to do — the theme still applies for this session.
    }
  }, [preference, resolved]);

  const cycle = useCallback(() => {
    setPreference((current) => {
      const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
      return next ?? "system";
    });
  }, []);

  return { preference, resolved, setPreference, cycle };
}
