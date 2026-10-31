/** Hosted builds follow the HTML base path; root localhost builds use the development API. */
export function getApiBase(): string {
  const base = new URL(document.baseURI);
  const path = base.pathname.replace(/\/+$/, '');
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname);
  if (local && !path) return 'http://127.0.0.1:8000';
  return `${base.origin}${path}`;
}
