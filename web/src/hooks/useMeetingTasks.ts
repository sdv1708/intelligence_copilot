import { useCallback, useState } from "react";

/**
 * Which meetings have a write in flight.
 *
 * `api/deps.py` holds a **per-meeting** lock across ingestion, deletion and a
 * whole brief run — tens of seconds for the last of those. Nothing on the
 * server rejects a second request for the same meeting; it blocks on the lock
 * and the browser shows a request that appears to hang. So the UI has to know
 * which meetings are busy and disable their write controls.
 *
 * Per meeting, not global, deliberately: an upload to one meeting must leave
 * every other meeting's controls alone, exactly as the server's lock does.
 */
export interface MeetingTasks {
  isBusy: (meetingId: string) => boolean;
  /**
   * Run `task` with the meeting marked busy. The mark clears however the task
   * ends, including on a throw — the caller still gets the rejection.
   */
  run: <T>(meetingId: string, task: () => Promise<T>) => Promise<T>;
}

export function useMeetingTasks(): MeetingTasks {
  // A count rather than a flag: two writes to one meeting should not happen,
  // because the controls are disabled, but if one ever slipped through then
  // the first to finish must not clear the mark the second is still holding.
  const [running, setRunning] = useState<Readonly<Record<string, number>>>({});

  const isBusy = useCallback(
    (meetingId: string) => (running[meetingId] ?? 0) > 0,
    [running],
  );

  const run = useCallback(
    async <T,>(meetingId: string, task: () => Promise<T>): Promise<T> => {
      setRunning((current) => ({
        ...current,
        [meetingId]: (current[meetingId] ?? 0) + 1,
      }));
      try {
        return await task();
      } finally {
        setRunning((current) => {
          const next = (current[meetingId] ?? 1) - 1;
          if (next > 0) return { ...current, [meetingId]: next };
          const { [meetingId]: _done, ...rest } = current;
          return rest;
        });
      }
    },
    [],
  );

  return { isBusy, run };
}
