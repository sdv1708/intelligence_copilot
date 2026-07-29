/**
 * The typed client. Fourteen operations, one per route in `api/routes/`.
 *
 * Every URL is relative. In development Vite proxies `/api` to the FastAPI
 * process (see `vite.config.ts`); in production FastAPI serves this bundle
 * itself. Same origin either way, so there is no base URL to configure and no
 * CORS to negotiate.
 */

import { ApiError, readErrorBody } from "./errors";
import type {
  BriefResponse,
  BriefStub,
  Health,
  IngestOutcome,
  IngestResponse,
  MaterialOut,
  MeetingCreate,
  MeetingOut,
  QaResponse,
} from "./types";

export interface RequestOptions {
  /**
   * Cancels the request. Worth passing from any effect: React's StrictMode
   * runs effects twice in development, and a brief takes tens of seconds, so an
   * abandoned request is not hypothetical.
   */
  signal?: AbortSignal;
}

/** Marker for a route that answers 204 with no body. */
type Empty = void;

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return null;
  }

  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("json")) {
    // A non-JSON body from an API route means something upstream answered
    // instead — a proxy error page, or the SPA fallback if its `/api` scoping
    // ever regressed. Keep the text; it is the only clue.
    const text = await response.text();
    return text ? { detail: text.slice(0, 500) } : null;
  }

  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function request<T>(
  path: string,
  init: RequestInit,
  options: RequestOptions,
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(path, {
      ...init,
      ...(options.signal ? { signal: options.signal } : {}),
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (cause) {
    // An abort is the caller's own doing, not a failure to report.
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new ApiError({
      message:
        "Could not reach the API. Start it with " +
        "`.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077`.",
      status: 0,
      url: path,
    });
  }

  const body = await parseBody(response);

  if (!response.ok) {
    const { message, kind, issues } = readErrorBody(body);
    throw new ApiError({
      message: message ?? `${response.status} ${response.statusText}`.trim(),
      status: response.status,
      url: path,
      kind,
      issues,
    });
  }

  return body as T;
}

function get<T>(path: string, options: RequestOptions): Promise<T> {
  return request<T>(path, { method: "GET" }, options);
}

function send<T>(
  method: "POST" | "DELETE",
  path: string,
  payload: unknown,
  options: RequestOptions,
): Promise<T> {
  return request<T>(
    path,
    payload === undefined
      ? { method }
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
    options,
  );
}

/** Path segments are ids from the server, but encoding them costs nothing. */
const seg = encodeURIComponent;

// --- Status -----------------------------------------------------------------

export function getHealth(options: RequestOptions = {}): Promise<Health> {
  return get<Health>("/api/health", options);
}

// --- Meetings ---------------------------------------------------------------

export function listMeetings(options: RequestOptions = {}): Promise<MeetingOut[]> {
  return get<MeetingOut[]>("/api/meetings", options);
}

export function createMeeting(
  payload: MeetingCreate,
  options: RequestOptions = {},
): Promise<MeetingOut> {
  return send<MeetingOut>("POST", "/api/meetings", payload, options);
}

export function getMeeting(
  meetingId: string,
  options: RequestOptions = {},
): Promise<MeetingOut> {
  return get<MeetingOut>(`/api/meetings/${seg(meetingId)}`, options);
}

export function deleteMeeting(
  meetingId: string,
  options: RequestOptions = {},
): Promise<Empty> {
  return send<Empty>("DELETE", `/api/meetings/${seg(meetingId)}`, undefined, options);
}

// --- Materials --------------------------------------------------------------

export function listMaterials(
  meetingId: string,
  options: RequestOptions = {},
): Promise<MaterialOut[]> {
  return get<MaterialOut[]>(`/api/meetings/${seg(meetingId)}/materials`, options);
}

/**
 * Upload one or more files.
 *
 * No `Content-Type` header: the browser has to set it, because only it knows
 * the multipart boundary. Setting it by hand produces a body FastAPI cannot
 * parse and a 422 that blames the files.
 *
 * The response is per-file. A corrupt PDF alongside three good decks costs you
 * the PDF and nothing else, so read `results` rather than assuming a 200 means
 * everything landed.
 */
export function uploadMaterials(
  meetingId: string,
  files: File[],
  options: RequestOptions = {},
): Promise<IngestResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file, file.name);
  }
  return request<IngestResponse>(
    `/api/meetings/${seg(meetingId)}/materials`,
    { method: "POST", body: form },
    options,
  );
}

export function pasteMaterial(
  meetingId: string,
  text: string,
  filename = "pasted_text.txt",
  options: RequestOptions = {},
): Promise<IngestOutcome> {
  return send<IngestOutcome>(
    "POST",
    `/api/meetings/${seg(meetingId)}/materials/text`,
    { text, filename },
    options,
  );
}

export function deleteMaterial(
  materialId: string,
  options: RequestOptions = {},
): Promise<Empty> {
  return send<Empty>("DELETE", `/api/materials/${seg(materialId)}`, undefined, options);
}

// --- Briefs -----------------------------------------------------------------

/**
 * Run the brief graph. Tens of seconds, and it holds the meeting's lock for all
 * of them — the UI must disable that meeting's upload controls while it runs
 * rather than letting requests queue invisibly.
 */
export function generateBrief(
  meetingId: string,
  options: RequestOptions = {},
): Promise<BriefResponse> {
  return send<BriefResponse>(
    "POST",
    `/api/meetings/${seg(meetingId)}/brief`,
    undefined,
    options,
  );
}

export function listBriefs(
  meetingId: string,
  options: RequestOptions = {},
): Promise<BriefStub[]> {
  return get<BriefStub[]>(`/api/meetings/${seg(meetingId)}/briefs`, options);
}

/** The most recent stored brief. 404 when the meeting has none yet. */
export function getLatestBrief(
  meetingId: string,
  options: RequestOptions = {},
): Promise<BriefResponse> {
  return get<BriefResponse>(`/api/meetings/${seg(meetingId)}/brief/latest`, options);
}

export function getBrief(
  briefId: string,
  options: RequestOptions = {},
): Promise<BriefResponse> {
  return get<BriefResponse>(`/api/briefs/${seg(briefId)}`, options);
}

// --- Q&A --------------------------------------------------------------------

export function askQuestion(
  meetingId: string,
  question: string,
  options: RequestOptions = {},
): Promise<QaResponse> {
  return send<QaResponse>(
    "POST",
    `/api/meetings/${seg(meetingId)}/qa`,
    { question },
    options,
  );
}

export { ApiError } from "./errors";
export type { ErrorKind, ValidationIssue } from "./errors";
export * from "./types";
