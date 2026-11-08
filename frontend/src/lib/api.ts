/** Thin fetch wrapper. Same-origin only; the session lives in an httpOnly cookie, and every
 *  state-changing request carries the per-session CSRF token in a header. */
let csrfToken = "";
export const setCsrfToken = (t: string) => { csrfToken = t; };

export class ApiError extends Error {
  status: number;
  fields: Record<string, string>;
  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

async function request<T>(method: string, url: string, body?: unknown, opts: { form?: FormData; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  let payload: BodyInit | undefined;
  if (opts.form) payload = opts.form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (res.status === 401 && opts.auth !== false && onUnauthorized) onUnauthorized();
  const data = res.headers.get("content-type")?.includes("application/json") ? await res.json() : null;
  if (!res.ok) {
    const detail = data?.detail;
    if (typeof detail === "string") throw new ApiError(res.status, detail);
    if (detail && typeof detail === "object") throw new ApiError(res.status, detail.message ?? "Request failed.", detail.fields ?? {});
    throw new ApiError(res.status, "Something went wrong. Please try again.");
  }
  return data as T;
}

export const api = {
  get: <T>(url: string, opts?: { auth?: boolean }) => request<T>("GET", url, undefined, opts),
  post: <T>(url: string, body?: unknown, opts?: { auth?: boolean }) => request<T>("POST", url, body, opts),
  postForm: <T>(url: string, form: FormData) => request<T>("POST", url, undefined, { form, auth: false }),
};
