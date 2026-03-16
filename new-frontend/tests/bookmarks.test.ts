import { describe, expect, it, vi } from "vitest";
import { loadBookmarks, saveBookmarks, toggleBookmark } from "@/lib/bookmarks";

describe("bookmark helpers", () => {
  it("toggles a bookmark on and off", () => {
    expect(toggleBookmark([], "paper-1")).toEqual(["paper-1"]);
    expect(toggleBookmark(["paper-1"], "paper-1")).toEqual([]);
  });

  it("saves and loads bookmarks from localStorage", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    saveBookmarks(["paper-1", "paper-2"]);
    expect(setItem).toHaveBeenCalled();

    window.localStorage.setItem("paperlens:bookmarks", JSON.stringify(["paper-3"]));
    expect(loadBookmarks()).toEqual(["paper-3"]);
  });
});
