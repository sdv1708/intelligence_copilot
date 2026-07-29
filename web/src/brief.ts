/**
 * Taking a brief out of the browser.
 *
 * A brief is read once in the app and then pasted into an agenda, a ticket or a
 * mail, so both exports exist for different destinations: Markdown for the
 * paste, JSON for anything that has to read it back. Both are pure functions
 * over the response plus one DOM helper, so the serialisation is testable
 * without a browser even though nothing tests it yet.
 */

import type { BriefResponse, MeetingBrief, Trace } from "./api/client";

// --- Markdown ---------------------------------------------------------------

/**
 * `undefined` drops the line; `""` keeps a blank one. Building the document as
 * a sparse array and filtering at the end is what keeps every section from
 * needing its own "and a blank line if the section above rendered" condition.
 */
type Line = string | undefined;

/**
 * A section, kept even when it is empty.
 *
 * `empty` is what the section says when it has nothing in it, and every section
 * a brief can legitimately leave blank supplies one. Dropping the heading
 * instead would make "the model found no action items" and "this export forgot
 * the action items" look identical on the page — the same silent loss the
 * screen already avoids by saying it in words.
 */
function heading(text: string, lines: Line[], empty?: string): Line[] {
  if (lines.length) return ["", `## ${text}`, "", ...lines];
  return empty ? ["", `## ${text}`, "", `_${empty}_`] : [];
}

function actionItems(brief: MeetingBrief): Line[] {
  return brief.open_action_items.map((item) => {
    // Real rows hold `"TBD"` and a null due date. Saying "no owner" is more
    // honest than an empty bold span that reads as a formatting bug.
    const owner = item.owner.trim() || "no owner";
    const due = item.due ? `, due ${item.due}` : "";
    return `- **${owner}** — ${item.item} _(${item.status}${due})_`;
  });
}

function agenda(brief: MeetingBrief): Line[] {
  if (!brief.proposed_agenda.length) return [];
  const total = brief.proposed_agenda.reduce((sum, item) => sum + item.minutes, 0);
  return [
    "| Topic | Minutes | Owner |",
    "| --- | --- | --- |",
    // A pipe inside a topic would end the cell early, and the model writes
    // long free text into that field.
    ...brief.proposed_agenda.map(
      (item) =>
        `| ${item.topic.replaceAll("|", "\\|")} | ${item.minutes} | ${
          item.owner?.trim() || "—"
        } |`,
    ),
    "",
    `Total: ${total} minutes.`,
  ];
}

function evidence(brief: MeetingBrief): Line[] {
  return brief.evidence.map(
    (entry, index) =>
      `${index + 1}. \`${entry.source}\` — ${entry.snippet
        // Snippets carry the source document's newlines. Collapsing them keeps
        // each citation one numbered list item rather than breaking the list.
        .replace(/\s+/g, " ")
        .trim()}`,
  );
}

function traceSection(trace: Trace): Line[] {
  const plan = trace.plan.map(
    (task) =>
      `- **${task.name}** — ${task.is_sweep ? "swept the whole meeting" : `searched "${task.query}"`}` +
      (task.rationale ? `. ${task.rationale}` : ""),
  );

  const findings = trace.findings.map((finding) =>
    finding.ok
      ? `- **${finding.name}** — ${finding.hits} hit(s), ${finding.neighbours} neighbour(s)`
      : `- **${finding.name}** — failed: ${finding.error ?? "no reason given"}`,
  );

  return [
    "",
    "## How this brief was produced",
    "",
    `Plan source: ${trace.plan_source || "unknown"}.` +
      (trace.plan_rationale ? ` ${trace.plan_rationale}` : ""),
    ...heading("Plan", plan),
    ...heading("Findings", findings),
    "",
    `${trace.chunks} chunk(s) reached synthesis.`,
    ...heading(
      "Timeline",
      trace.notes.map((note) => `- ${note}`),
    ),
  ];
}

/**
 * The whole of what the panel is showing, as one Markdown document.
 *
 * The trace goes in as an appendix when there is one. A brief recalled from
 * storage has no trace, and the export says nothing about it rather than
 * printing an empty section — same distinction the panel draws on screen.
 */
export function briefToMarkdown(response: BriefResponse): string {
  const brief = response.brief;
  if (!brief) {
    return `# Brief failed\n\n${response.warning ?? "No reason was given."}\n`;
  }

  const meta = [
    response.stored_at ? `Stored ${response.stored_at}` : "Not stored",
    response.model ? `model ${response.model}` : null,
    brief.time_window ? `covering ${brief.time_window}` : null,
  ].filter(Boolean);

  const lines: Line[] = [
    `# ${brief.meeting_title.trim() || "Untitled meeting"}`,
    "",
    `_${meta.join(" · ")}_`,
    ...heading(
      "Recap",
      brief.last_meeting_recap.trim() ? [brief.last_meeting_recap.trim()] : [],
      "No previous meeting was found to recap.",
    ),
    ...heading(
      "Open action items",
      actionItems(brief),
      "Nothing outstanding was found in the documents.",
    ),
    ...heading(
      "Key topics",
      brief.key_topics_today.map((topic) => `- ${topic}`),
      "No topics were proposed.",
    ),
    ...heading("Proposed agenda", agenda(brief), "No agenda was proposed."),
    ...heading(
      "Evidence",
      evidence(brief),
      "Nothing was cited; this brief was not written from retrieved text.",
    ),
    ...(response.warning ? ["", `> Warning: ${response.warning}`] : []),
    ...(response.trace ? traceSection(response.trace) : []),
    "",
  ];

  return lines.filter((line) => line !== undefined).join("\n");
}

// --- Downloading ------------------------------------------------------------

/** Enough of a slug to make a filename out of a meeting title. */
function slug(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "brief"
  );
}

export function briefFilename(response: BriefResponse, extension: string): string {
  const title = slug(response.brief?.meeting_title ?? "brief");
  // The id disambiguates the several briefs a meeting accumulates; a run that
  // failed to store has none, so fall back to the day.
  const stamp = response.brief_id ?? new Date().toISOString().slice(0, 10);
  return `${title}-${stamp}.${extension}`;
}

/**
 * Save `text` as a file.
 *
 * The anchor is attached to the document before it is clicked: a detached one
 * is ignored by Firefox. The object URL is revoked on the next tick rather than
 * immediately, because revoking it in the same task can cancel the download the
 * click just started.
 */
export function download(filename: string, mime: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
