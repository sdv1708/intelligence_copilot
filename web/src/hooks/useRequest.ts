import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../api/client";
import type { RequestOptions } from "../api/client";

/**
 * A request has three outcomes and the UI has to render all three, so they are
 * a discriminated union rather than a `data`/`error`/`loading` triple where
 * every combination is representable and most are impossible.
 */
export type RequestState<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "failed"; error: ApiError };

export interface Request<T> {
  state: RequestState<T>;
  reload: () => void;
}

/**
 * Run one request on mount, and again whenever `reload` is called.
 *
 * The fetcher takes `RequestOptions` and must pass them through: the effect
 * aborts in cleanup, which is what stops StrictMode's double-invoked effect
 * from racing its own first response into the state.
 */
export function useRequest<T>(
  fetcher: (options: RequestOptions) => Promise<T>,
  deps: readonly unknown[] = [],
): Request<T> {
  const [state, setState] = useState<RequestState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    fetcher({ signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "failed",
          error:
            error instanceof ApiError
              ? error
              : new ApiError({
                  message: error instanceof Error ? error.message : String(error),
                  status: 0,
                  url: "",
                }),
        });
      });

    return () => controller.abort();
    // `fetcher` is deliberately absent from the dependencies: callers pass an
    // inline closure, so depending on it would refetch on every render. What
    // the request actually varies with goes in `deps`.
  }, [attempt, ...deps]);

  return { state, reload };
}
