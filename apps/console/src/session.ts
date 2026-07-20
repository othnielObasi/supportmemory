const accessTokenKey = "supportmemory.access_token";
const tenantKeys = ["sm.organisation", "sm.workspace", "sm.project", "sm.environment"];

export function privateLoginPath(): string {
  const next = `${window.location.pathname}${window.location.search}`;
  return `/login?next=${encodeURIComponent(next)}`;
}

export function clearPrivateSession(): void {
  sessionStorage.removeItem(accessTokenKey);
  tenantKeys.forEach((key) => localStorage.removeItem(key));
}

export function signOut(): void {
  clearPrivateSession();
  window.location.assign("/login");
}

export async function authenticatedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 401) {
    clearPrivateSession();
    window.location.replace(privateLoginPath());
  }
  return response;
}
