import { FileText, Trash2 } from "lucide-react";
import { useState } from "react";

import { asApiError, deleteMaterial } from "../api/client";
import type { ApiError, MaterialOut } from "../api/client";
import { formatCount, formatDay } from "../format";
import type { MeetingTasks } from "../hooks/useMeetingTasks";
import { Button, ErrorNote } from "./controls";

interface MaterialsListProps {
  meetingId: string;
  materials: MaterialOut[];
  /** True while this meeting holds the server's lock for something else. */
  busy: boolean;
  run: MeetingTasks["run"];
  onDeleted: () => void;
}

/**
 * The documents a brief is built from.
 *
 * A list rather than a table: at 375px a four-column table either scrolls
 * sideways or crushes the filename, and the filename is the only column anyone
 * scans by.
 */
export function MaterialsList({
  meetingId,
  materials,
  busy,
  run,
  onDeleted,
}: MaterialsListProps) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function remove(materialId: string) {
    setConfirming(null);
    setError(null);
    try {
      // Through `run` because deletion takes the same per-meeting lock as
      // ingestion: it drops the chunk rows and rewrites the vector index.
      await run(meetingId, () => deleteMaterial(materialId));
      onDeleted();
    } catch (cause) {
      setError(asApiError(cause));
    }
  }

  if (materials.length === 0) {
    return (
      <p className="rounded-xl border border-line bg-panel px-4 py-6 text-sm leading-relaxed text-muted">
        Nothing added yet. A brief needs at least one document to read.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error ? <ErrorNote error={error} /> : null}

      <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-panel">
        {materials.map((material) => (
          <li key={material.id} className="flex items-center gap-3 px-4 py-3">
            <FileText
              size={16}
              strokeWidth={1.75}
              aria-hidden="true"
              className="shrink-0 text-faint"
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-ink">{material.filename}</p>
              <p className="mt-0.5 text-xs text-muted">
                {material.media_type} · {formatCount(material.char_count)}{" "}
                characters · {formatDay(material.created_at)}
              </p>
            </div>

            {confirming === material.id ? (
              <div className="flex shrink-0 items-center gap-1.5">
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => void remove(material.id)}
                  disabled={busy}
                >
                  Delete
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setConfirming(material.id)}
                disabled={busy}
                aria-label={`Delete ${material.filename}`}
                title="Delete"
              >
                <Trash2 size={14} strokeWidth={1.75} aria-hidden="true" />
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
