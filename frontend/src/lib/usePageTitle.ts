import { useEffect } from "react";

/** Sets the browser-tab title for an admin page, restoring it on unmount. */
export function usePageTitle(title: string) {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · AcciAssist Admin`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
