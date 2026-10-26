import { useEffect, useState } from "react";

/** How long typing has to pause before an edit is sent to the API. */
export const EDIT_PAUSE_MS = 350;

export function useDebounced<T>(value: T, ms = EDIT_PAUSE_MS): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return settled;
}
