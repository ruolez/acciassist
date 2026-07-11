// Mirrors _TOKEN in backend/app/services/summary.py — keep the two in sync.
const TOKEN_RE = /\{\{\s*([a-zA-Z0-9_-]+)\s*\}\}/g;

/** Tokens in the template body that match no question slug (deduped, in
 * order of appearance). The backend renders these as blank text. */
export function findUnknownTokens(body: string, knownSlugs: Set<string>): string[] {
  const unknown: string[] = [];
  for (const match of body.matchAll(TOKEN_RE)) {
    const slug = match[1];
    if (!knownSlugs.has(slug) && !unknown.includes(slug)) {
      unknown.push(slug);
    }
  }
  return unknown;
}
