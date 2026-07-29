import { useState } from "react";

import { ApiError, createMeeting } from "../api/client";
import type { MeetingOut } from "../api/client";
import { parseList } from "../format";
import { Button, ErrorNote, Field, INPUT } from "./controls";

interface NewMeetingProps {
  onCreated: (meeting: MeetingOut) => void;
  onCancel: () => void;
}

/**
 * The create form.
 *
 * A view rather than a dialog: the sidebar is 17rem wide and this has four
 * fields, and a full-column form needs no focus trap to be usable with a
 * keyboard.
 */
export function NewMeeting({ onCreated, onCancel }: NewMeetingProps) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [attendees, setAttendees] = useState("");
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  // The server enforces `min_length=1` after stripping, so a title of spaces
  // is a 422. Matching that here keeps the button honest about what it will do.
  const ready = title.trim().length > 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!ready || saving) return;

    setSaving(true);
    setError(null);
    try {
      const meeting = await createMeeting({
        title,
        date: date.trim() || null,
        attendees: parseList(attendees),
        tags: parseList(tags),
      });
      onCreated(meeting);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause
          : new ApiError({
              message: cause instanceof Error ? cause.message : String(cause),
              status: 0,
              url: "",
            }),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          New meeting
        </h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          Only a title is required. Everything else is context the brief can
          draw on, and can be left empty.
        </p>
      </div>

      {error ? <ErrorNote error={error} /> : null}

      <form onSubmit={submit} className="flex flex-col gap-5">
        <Field id="meeting-title" label="Title">
          <input
            id="meeting-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={300}
            autoFocus
            required
            placeholder="Weekly engineering sync"
            className={INPUT}
          />
        </Field>

        <Field
          id="meeting-date"
          label="Date"
          hint="Free text — the server stores it as written. Real rows hold both dates and words like “Today”."
        >
          <input
            id="meeting-date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            maxLength={32}
            placeholder="2026-08-05"
            className={INPUT}
          />
        </Field>

        <Field
          id="meeting-attendees"
          label="Attendees"
          hint="Comma separated. Stored as one field, so a name containing a comma will come back split."
        >
          <input
            id="meeting-attendees"
            value={attendees}
            onChange={(event) => setAttendees(event.target.value)}
            placeholder="Ana, Rui, Sam"
            className={INPUT}
          />
        </Field>

        <Field id="meeting-tags" label="Tags" hint="Comma separated.">
          <input
            id="meeting-tags"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            placeholder="planning, q4"
            className={INPUT}
          />
        </Field>

        <div className="flex items-center gap-2">
          <Button type="submit" variant="primary" busy={saving} disabled={!ready}>
            Create meeting
          </Button>
          <Button onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}
