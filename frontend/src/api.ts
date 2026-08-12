// Tiny typed fetch client. Everything goes through /api (Vite proxies to :8000).

export type Account = {
  id: number; brand_id: number; platform: string; handle: string; status: string;
};
export type Brand = {
  id: number; name: string; initials: string; color: string; voice: string;
  never_say: string; cta: string; audience: string; always_say: string; pillars: string;
};
export type Post = {
  id: number; brand_id: number; account_id: number | null; format: string;
  title: string; caption: string; status: string; created_by: string;
  current_version: number; platform?: string; handle?: string; media_url?: string;
  versions?: any[]; approvals?: any[]; jobs?: any[]; violations?: string[];
};
export type Job = {
  id: number; post_id: number; account_id: number; platform: string;
  scheduled_at: string; status: string; attempts: number; last_error: string;
  platform_post_id: string; platform_url: string; published_at: string | null;
  title?: string; format?: string; handle?: string;
};

export type FeedPost = {
  id: number; author_name: string; author_handle: string; author_initials: string; author_color: string;
  platform: string; text: string; media: string; likes: number; reposts: number; comments_count: number;
  liked: number; reposted: number; created_at: string;
};
export type FeedComment = { id: number; feed_post_id: number; author: string; initials: string; text: string; created_at: string };
export type Person = { id: number; handle: string; name: string; initials: string; color: string; bio: string; following: number; suggested: number };
export type Notification = { id: number; type: string; actor_name: string; actor_initials: string; actor_color: string; text: string; read: number; created_at: string };
// Result of mirroring a feed engagement back onto the post's origin platform.
export type Mirror = { mirrored: boolean; platform: string; detail: string; platform_ref?: string };

async function req(method: string, path: string, body?: unknown) {
  const res = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = data.detail ?? JSON.stringify(data);
    } catch {
      /* keep statusText */
    }
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  state: () => req("GET", "/state"),
  posts: (status?: string) => req("GET", "/posts" + (status ? `?status=${status}` : "")),
  post: (id: number) => req("GET", `/posts/${id}`),
  createPost: (b: any) => req("POST", "/posts", b),
  editPost: (id: number, b: any) => req("PATCH", `/posts/${id}`, b),
  submit: (id: number, actor: string) => req("POST", `/posts/${id}/submit`, { actor }),
  approve: (id: number, actor: string) => req("POST", `/posts/${id}/approve`, { actor }),
  requestChanges: (id: number, actor: string, comment: string) =>
    req("POST", `/posts/${id}/request-changes`, { actor, comment }),
  schedule: (id: number, scheduled_at: string, account_ids?: number[]) =>
    req("POST", `/posts/${id}/schedule`, { scheduled_at, account_ids }),
  publishNow: (id: number) => req("POST", `/posts/${id}/publish-now`, {}),
  calendar: (start?: string, end?: string) =>
    req("GET", "/calendar" + (start ? `?start=${start}&end=${end}` : "")),
  jobs: (status?: string) => req("GET", "/jobs" + (status ? `?status=${status}` : "")),
  runDue: () => req("POST", "/jobs/run-due", {}),
  cancelJob: (id: number) => req("POST", `/jobs/${id}/cancel`, {}),
  generate: (b: any) => req("POST", "/ai/generate", b),
  analyst: (question: string) => req("POST", "/ai/analyst", { question }),
  analytics: () => req("GET", "/analytics/summary"),
  recommendations: () => req("GET", "/recommendations"),
  createFromRec: (b: any) => req("POST", "/create-from-recommendation", b),
  updateBrand: (id: number, b: any) => req("PATCH", `/brands/${id}`, b),
  metaCheck: () => req("GET", "/integrations/meta/check"),
  feed: () => req("GET", "/feed"),
  feedCreate: (text: string, media = "", platforms: string[] = []) => req("POST", "/feed", { text, media, platforms }),
  feedLike: (id: number) => req("POST", `/feed/${id}/like`, {}),
  feedRepost: (id: number) => req("POST", `/feed/${id}/repost`, {}),
  feedComments: (id: number) => req("GET", `/feed/${id}/comments`),
  feedComment: (id: number, text: string) => req("POST", `/feed/${id}/comment`, { text }),
  people: () => req("GET", "/people"),
  follow: (handle: string) => req("POST", `/people/${handle}/follow`, {}),
  notifications: () => req("GET", "/notifications"),
  readNotifications: () => req("POST", "/notifications/read", {}),
  profile: () => req("GET", "/profile"),
  reset: () => req("POST", "/admin/reset", {}),
};
