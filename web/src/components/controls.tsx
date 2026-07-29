import { Loader2, TriangleAlert } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { ApiError } from "../api/client";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const BASE =
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md " +
  "font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45";

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-paper hover:bg-accent-ink",
  secondary: "border border-line-strong text-ink hover:bg-panel",
  // Outlined rather than filled: a destructive control should be legible at a
  // glance without competing with the accent for attention.
  danger: "border border-crit/45 text-crit hover:bg-crit/10",
  ghost: "text-muted hover:bg-line hover:text-ink",
};

const SIZE = {
  sm: "h-8 px-2.5 text-xs",
  md: "h-9 px-3.5 text-sm",
} as const;

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: keyof typeof SIZE;
  /** Shows a spinner in place of any icon and disables the control. */
  busy?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  busy = false,
  disabled,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || busy}
      className={`${BASE} ${VARIANT[variant]} ${SIZE[size]} ${className}`}
      {...rest}
    >
      {busy ? (
        <Loader2
          size={14}
          strokeWidth={1.75}
          aria-hidden="true"
          className="animate-spin"
        />
      ) : null}
      {children}
    </button>
  );
}

/**
 * A failed request, said in words rather than as a status code.
 *
 * `kind` carries the `core.exceptions` class the server raised, and the two
 * that matter here mean different things to whoever is looking: a meeting that
 * no longer exists is not something to retry, and a missing key is for whoever
 * runs the server rather than whoever is clicking.
 */
export function ErrorNote({
  error,
  onRetry,
  className = "",
}: {
  error: ApiError;
  onRetry?: () => void;
  className?: string;
}) {
  const retryable = !error.isConfiguration && error.kind !== "MeetingNotFoundError";

  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-lg border border-crit/40 px-4 py-3 ${className}`}
    >
      <TriangleAlert
        size={16}
        strokeWidth={1.75}
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-crit"
      />
      <p className="min-w-0 flex-1 text-sm leading-relaxed text-ink">
        {error.message}
      </p>
      {onRetry && retryable ? (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

/** A labelled text input, with the label tied to the field by id. */
export function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {hint ? <p className="text-xs leading-relaxed text-muted">{hint}</p> : null}
    </div>
  );
}

/** Shared input chrome, so a textarea and an input do not drift apart. */
export const INPUT =
  "w-full rounded-md border border-line-strong bg-paper px-3 py-2 text-sm " +
  "text-ink placeholder:text-faint disabled:opacity-45";
