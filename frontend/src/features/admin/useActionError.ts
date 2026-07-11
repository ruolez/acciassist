import { useCallback, useState } from "react";

import { ApiError } from "../../api/client";

/** Consistent error state for admin mutations: pass `onError` to useMutation
 * and call `clear` from onSuccess; render `error` as a banner. */
export function useActionError() {
  const [error, setError] = useState<string | null>(null);
  const onError = useCallback((e: unknown, fallback = "Something went wrong") => {
    setError(e instanceof ApiError ? e.message : fallback);
  }, []);
  const clear = useCallback(() => setError(null), []);
  return { error, onError, clear };
}
