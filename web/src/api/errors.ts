/**
 * One error type for every way a request can fail.
 *
 * The API answers with three different bodies and `detail` is not always a
 * string, so rendering `error.detail` straight from the response prints
 * `[object Object]` the first time a form fails validation:
 *
 * | Source                      | Status | Body                                        |
 * |-----------------------------|--------|---------------------------------------------|
 * | Pydantic request validation | 422    | `{ detail: [{ type, loc, msg, ... }, ...] }` |
 * | `HTTPException`             | 404/422| `{ detail: "..." }`                          |
 * | `CopilotError`              | mapped | `{ detail: "...", kind: "..." }`             |
 * | Unmatched route             | 404    | `{ detail: "Not Found" }`                    |
 *
 * Normalising them here means the UI reads `error.message` to say something and
 * `error.kind` to say something *specific* — "no API key" rather than "request
 * failed". `kind` is built inline by `api/errors.py:handle_copilot_error` and
 * is not declared in `api/schemas.py`, which is why it is documented here.
 */

/** One entry of Pydantic's 422 list. */
export interface ValidationIssue {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

/**
 * The name of the `core.exceptions` class the server raised, when it raised
 * one. Anything else — a plain `HTTPException`, an unmatched route — has none.
 */
export type ErrorKind =
  /**
   * Not a `core.exceptions` class: the Vite dev proxy uses it to say the API is
   * not listening. Without it, a connection refused arrives as the proxy's own
   * 500 and reads as "the API answered badly" rather than "it is not running".
   */
  | "ApiUnreachable"
  | "ConfigurationError"
  | "EmptyDocumentError"
  | "IngestionError"
  | "InvalidBriefError"
  | "MeetingNotFoundError"
  | "RetrievalError"
  | "StorageError"
  | "SynthesisError"
  | "UnsupportedFileTypeError"
  | (string & {});

export class ApiError extends Error {
  /** The HTTP status, or 0 when the request never reached the server. */
  readonly status: number;
  readonly kind: ErrorKind | null;
  /** Non-empty only for a Pydantic validation failure. */
  readonly issues: ValidationIssue[];
  readonly url: string;

  constructor(init: {
    message: string;
    status: number;
    url: string;
    kind?: ErrorKind | null;
    issues?: ValidationIssue[];
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.url = init.url;
    this.kind = init.kind ?? null;
    this.issues = init.issues ?? [];
  }

  /**
   * The API was never reached — either the request itself failed, or the dev
   * proxy could not connect. Not `status === 502` alone: a real 502 from the
   * API means the *provider* failed, and it carries `kind: "SynthesisError"`.
   */
  get isOffline(): boolean {
    return this.status === 0 || this.kind === "ApiUnreachable";
  }

  /**
   * The server is misconfigured rather than broken: no API key, an unknown
   * provider, a missing prompt file. Fixable by whoever runs the server, so the
   * UI should say so instead of offering a retry.
   */
  get isConfiguration(): boolean {
    return this.status === 503 || this.kind === "ConfigurationError";
  }
}

/**
 * Render one Pydantic issue as a line a person can act on.
 *
 * `loc` starts with the request part — `["body", "title"]` — which is noise to
 * anyone looking at a form, so the first segment is dropped.
 */
export function describeIssue(issue: ValidationIssue): string {
  const path = issue.loc.slice(1).join(".");
  return path ? `${path}: ${issue.msg}` : issue.msg;
}

interface ErrorBody {
  message: string | null;
  kind: ErrorKind | null;
  issues: ValidationIssue[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isIssue(value: unknown): value is ValidationIssue {
  return isRecord(value) && typeof value.msg === "string" && Array.isArray(value.loc);
}

/** Pull a message, a kind and any validation issues out of a response body. */
export function readErrorBody(body: unknown): ErrorBody {
  if (!isRecord(body)) {
    return { message: null, kind: null, issues: [] };
  }

  const kind = typeof body.kind === "string" ? body.kind : null;
  const detail = body.detail;

  if (typeof detail === "string") {
    return { message: detail, kind, issues: [] };
  }

  if (Array.isArray(detail)) {
    const issues = detail.filter(isIssue);
    return {
      message: issues.length ? issues.map(describeIssue).join("; ") : null,
      kind,
      issues,
    };
  }

  return { message: null, kind, issues: [] };
}
