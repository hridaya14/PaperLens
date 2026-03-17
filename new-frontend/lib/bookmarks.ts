const STORAGE_KEY = "paperlens:bookmarks";

export function loadBookmarks() {
  if (typeof window === "undefined") {
    return [] as string[];
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return Array.from(new Set(parsed.map((value) => String(value)).filter(Boolean)));
  } catch {
    return [];
  }
}

export function saveBookmarks(bookmarks: string[]) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(new Set(bookmarks))));
}

export function toggleBookmark(bookmarks: string[], paperId: string) {
  if (bookmarks.includes(paperId)) {
    return bookmarks.filter((id) => id !== paperId);
  }

  return [...bookmarks, paperId];
}
