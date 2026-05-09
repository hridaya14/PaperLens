const BOOKMARK_STORAGE_KEY = "paperlens:bookmarks";

export function loadBookmarks() {
  if (typeof window === "undefined") {
    return [] as string[];
  }

  const raw = window.localStorage.getItem(BOOKMARK_STORAGE_KEY);
  if (!raw) {
    return [] as string[];
  }

  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function saveBookmarks(bookmarks: string[]) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(BOOKMARK_STORAGE_KEY, JSON.stringify(bookmarks));
}

export function toggleBookmark(current: string[], paperId: string) {
  const next = new Set(current);
  if (next.has(paperId)) {
    next.delete(paperId);
  } else {
    next.add(paperId);
  }

  return Array.from(next);
}
