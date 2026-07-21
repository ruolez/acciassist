import { useEffect } from "react";

/** Sets the browser-tab title, restoring it on unmount. */
export function usePageTitle(title: string, suffix = "AcciAssist Admin") {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · ${suffix}`;
    return () => {
      document.title = previous;
    };
  }, [title, suffix]);
}
