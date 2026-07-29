/**
 * The wire format, hand-written from `api/schemas.py` and `core/schema.py`.
 *
 * Hand-written rather than generated on purpose: writing it out is the review
 * of the API surface, and the comments here record the things the JSON shape
 * cannot say — which fields are nullable because the database column is, and
 * which nulls carry meaning.
 *
 * Keep this file in step with `api/schemas.py`. `MeetingBrief` in particular is
 * re-exported by the API from `core/schema.py` rather than redeclared, so there
 * is exactly one Python definition of a brief and this is its one mirror.
 */

// --- Meetings ---------------------------------------------------------------

/** The body `POST /api/meetings` accepts. */
export interface MeetingCreate {
  title: string;
  /** Free text, not validated as a date. Real rows hold things like "Today". */
  date?: string | null;
  attendees?: string[];
  tags?: string[];
}

export interface MeetingOut {
  id: string;
  /**
   * Stored verbatim, including trailing spaces — the records layer does not
   * strip what was written. Trim at the point of display, not on the way in.
   */
  title: string;
  date: string | null;
  /** Split out of one comma-joined column, so usually short and often empty. */
  attendees: string[];
  tags: string[];
  created_at: string;
  material_count: number;
  brief_count: number;
}

// --- Materials --------------------------------------------------------------

export interface MaterialOut {
  id: string;
  meeting_id: string;
  /** Never null on the wire: the API substitutes "Untitled" for a null column. */
  filename: string;
  /** Likewise "unknown". `"pasted"` marks text typed in rather than uploaded. */
  media_type: string;
  /** Runs to six figures on real transcripts. Format with separators. */
  char_count: number;
  created_at: string;
}

export interface PasteRequest {
  text: string;
  filename?: string;
}

/**
 * What happened to one uploaded file.
 *
 * A multi-file upload is not all-or-nothing, so a batch can come back with
 * `ingested` and `failed` both non-zero and the per-file reasons in `results`.
 */
export interface IngestOutcome {
  filename: string;
  success: boolean;
  material_id: string | null;
  chunks: number;
  characters: number;
  error: string | null;
}

export interface IngestResponse {
  results: IngestOutcome[];
  ingested: number;
  failed: number;
}

// --- The trace --------------------------------------------------------------

/** One line of enquiry the supervisor decided to run. */
export interface TaskOut {
  name: string;
  query: string;
  rationale: string;
  is_sweep: boolean;
}

/**
 * What one specialist came back with.
 *
 * `hits` matched the query; `neighbours` were pulled in because they sit beside
 * a hit. Summing them would overstate what the search actually found.
 */
export interface FindingOut {
  name: string;
  query: string;
  ok: boolean;
  hits: number;
  neighbours: number;
  error: string | null;
}

export interface Trace {
  notes: string[];
  plan: TaskOut[];
  plan_source: string;
  plan_rationale: string;
  findings: FindingOut[];
  chunks: number;
}

// --- Briefs -----------------------------------------------------------------

export type ActionItemStatus = "open" | "blocked" | "done";

export interface ActionItem {
  owner: string;
  item: string;
  /** `YYYY-MM-DD` when present; the API rejects any other shape. */
  due: string | null;
  status: ActionItemStatus;
}

export interface AgendaItem {
  topic: string;
  minutes: number;
  owner: string | null;
}

/** A citation tying a statement back to source text. */
export interface Evidence {
  /** The human-readable `materialId#cN` label. */
  source: string;
  snippet: string;
  chunk_id: number | null;
}

export interface MeetingBrief {
  meeting_title: string;
  /** `YYYY-MM-DD..YYYY-MM-DD` when present. */
  time_window: string | null;
  last_meeting_recap: string;
  open_action_items: ActionItem[];
  key_topics_today: string[];
  proposed_agenda: AgendaItem[];
  evidence: Evidence[];
}

/** A row of the brief history, without the payload. */
export interface BriefStub {
  id: string;
  meeting_id: string;
  created_at: string;
  model: string;
}

export interface BriefResponse {
  /**
   * `ok` means a document exists. A run that produced a brief and then failed
   * to store it is `ok: true` with a `warning` — read both, or you will either
   * throw away a usable brief or hide the fact that it was not saved.
   */
  ok: boolean;
  brief: MeetingBrief | null;
  brief_id: string | null;
  provider: string;
  model: string;
  warning: string | null;
  failed_tasks: string[];
  /**
   * Null for a brief read back from storage, populated for one just generated.
   * That distinction is the point: it separates "recalled" from "generated and
   * found nothing", so do not default it to an empty trace.
   */
  trace: Trace | null;
  /** Set when the brief came from, or reached, the database. */
  stored_at: string | null;
}

// --- Q&A --------------------------------------------------------------------

export interface QaRequest {
  question: string;
}

export interface QaResponse {
  /**
   * Unlike a brief, an answer with an `error` is `ok: false` — the text in that
   * case is the "nothing retrieved" boilerplate, and reporting it as an answer
   * would disguise a broken index as a polite non-answer.
   */
  ok: boolean;
  answer: string;
  /** `materialId#cN` labels for the chunks the answer was drawn from. */
  sources: string[];
  provider: string;
  model: string;
  error: string | null;
  trace: Trace | null;
}

// --- Status -----------------------------------------------------------------

export interface Health {
  provider: string;
  model: string;
  /** Where the embedding model runs: "cuda", "mps" or "cpu". */
  device: string;
  /** Whether the supervisor plans with the LLM or falls back to a fixed plan. */
  supervisor: boolean;
  has_api_key: boolean;
  storage_dir: string;
  /**
   * True when `Settings.prepare_storage` silently relocated to a temp
   * directory because the configured one was unwritable — meaning nothing the
   * user creates survives a restart. Worth saying out loud.
   */
  storage_is_temporary: boolean;
}
