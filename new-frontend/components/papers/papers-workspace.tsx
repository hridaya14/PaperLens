"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpenText,
  Filter,
  LibraryBig,
  Search,
  Sparkles,
} from "lucide-react";
import { deletePaper, getPapers } from "@/lib/api/client";
import { AVAILABLE_CATEGORIES, RESULT_LIMITS } from "@/lib/constants";
import { loadBookmarks, saveBookmarks, toggleBookmark } from "@/lib/bookmarks";
import type { Paper } from "@/lib/schemas";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { FlashcardDialog } from "@/components/papers/flashcard-dialog";
import { MindMapDialog } from "@/components/papers/mindmap-dialog";
import { PaperCard } from "@/components/papers/paper-card";
import { PdfDialog } from "@/components/papers/pdf-dialog";
import { ProjectPickerDialog } from "@/components/projects/project-picker-dialog";

type SearchFilters = {
  query: string;
  categories: string[];
  pdfProcessed: boolean | null;
  source: string;
  limit: number;
};

const defaultFilters: SearchFilters = {
  query: "",
  categories: [],
  pdfProcessed: null,
  source: "any",
  limit: 20,
};

export function PapersWorkspace() {
  const queryClient = useQueryClient();
  const [draftFilters, setDraftFilters] =
    useState<SearchFilters>(defaultFilters);
  const [activeFilters, setActiveFilters] =
    useState<SearchFilters>(defaultFilters);
  const [bookmarks, setBookmarks] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"all" | "bookmarked">("all");
  const [pdfPaper, setPdfPaper] = useState<Paper | null>(null);
  const [mindMapPaper, setMindMapPaper] = useState<Paper | null>(null);
  const [flashcardPaper, setFlashcardPaper] = useState<Paper | null>(null);
  const [projectPickerPaper, setProjectPickerPaper] = useState<Paper | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    setBookmarks(loadBookmarks());
  }, []);

  useEffect(() => {
    saveBookmarks(bookmarks);
  }, [bookmarks]);

  const papersQuery = useQuery({
    queryKey: ["papers", activeFilters],
    queryFn: () =>
      getPapers({
        query: activeFilters.query || undefined,
        categories: activeFilters.categories,
        pdfProcessed: activeFilters.pdfProcessed,
        source:
          activeFilters.source === "any" ? undefined : activeFilters.source,
        limit: activeFilters.limit,
        offset: 0,
      }),
  });

  const papers = papersQuery.data?.papers ?? [];
  const visiblePapers =
    activeTab === "all"
      ? papers
      : papers.filter((paper) => bookmarks.includes(paper.id));

  const deletePaperMutation = useMutation({
    mutationFn: deletePaper,
  });

  function applyFilters() {
    setActiveFilters(draftFilters);
  }

  function resetFilters() {
    setDraftFilters(defaultFilters);
    setActiveFilters(defaultFilters);
  }

  async function handleDeletePaper(paper: Paper) {
    const confirmed = window.confirm(
      `Delete "${paper.title}"? This action cannot be undone.`,
    );

    if (!confirmed) {
      return;
    }

    setDeleteError(null);

    try {
      await deletePaperMutation.mutateAsync(paper.id);
      setBookmarks((current) => current.filter((bookmarkId) => bookmarkId !== paper.id));

      if (pdfPaper?.id === paper.id) {
        setPdfPaper(null);
      }

      if (mindMapPaper?.id === paper.id) {
        setMindMapPaper(null);
      }

      if (flashcardPaper?.id === paper.id) {
        setFlashcardPaper(null);
      }

      await queryClient.invalidateQueries({ queryKey: ["papers"] });
    } catch (error) {
      setDeleteError(
        error instanceof Error ? error.message : "Delete request failed",
      );
    }
  }

  function renderFilters() {
    return (
      <div className="space-y-6">
        <div>
          <Label htmlFor="query">Search by title</Label>
          <Input
            id="query"
            placeholder="Transformers, multimodal systems, retrieval..."
            value={draftFilters.query}
            onChange={(event) =>
              setDraftFilters((current) => ({
                ...current,
                query: event.target.value,
              }))
            }
            className="mt-2"
          />
        </div>

        <div className="space-y-3">
          <Label>Categories</Label>
          <div className="flex flex-wrap gap-2">
            {AVAILABLE_CATEGORIES.map((category) => {
              const active = draftFilters.categories.includes(category.value);
              return (
                <button
                  key={category.value}
                  type="button"
                  onClick={() =>
                    setDraftFilters((current) => ({
                      ...current,
                      categories: active
                        ? current.categories.filter(
                            (value) => value !== category.value,
                          )
                        : [...current.categories, category.value],
                    }))
                  }
                  className={`rounded-full border px-3 py-2 text-sm transition ${
                    active
                      ? "border-amber-300/20 bg-amber-300/12 text-amber-200"
                      : "border-white/10 bg-white/5 text-white/68 hover:bg-white/8 hover:text-white"
                  }`}
                >
                  {category.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="space-y-2">
            <span className="block text-sm font-medium text-foreground">
              PDF status
            </span>
            <select
              value={
                draftFilters.pdfProcessed === null
                  ? "any"
                  : draftFilters.pdfProcessed
                    ? "processed"
                    : "pending"
              }
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  pdfProcessed:
                    event.target.value === "processed"
                      ? true
                      : event.target.value === "pending"
                        ? false
                        : null,
                }))
              }
              className="field-surface h-12 w-full appearance-none rounded-2xl px-4 text-sm outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="any">Any</option>
              <option value="processed">Processed</option>
              <option value="pending">Not processed</option>
            </select>
          </label>

          <label className="space-y-2">
            <span className="block text-sm font-medium text-foreground">
              Source
            </span>
            <select
              value={draftFilters.source}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  source: event.target.value,
                }))
              }
              className="field-surface h-12 w-full appearance-none rounded-2xl px-4 text-sm outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="any">Any</option>
              <option value="arxiv">arXiv</option>
              <option value="user_upload">User uploads</option>
            </select>
          </label>

          <label className="space-y-2">
            <span className="block text-sm font-medium text-foreground">
              Results per page
            </span>
            <select
              value={draftFilters.limit}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  limit: Number(event.target.value),
                }))
              }
              className="field-surface h-12 w-full appearance-none rounded-2xl px-4 text-sm outline-none focus:ring-2 focus:ring-ring"
            >
              {RESULT_LIMITS.map((limit) => (
                <option key={limit} value={limit}>
                  {limit}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Button onClick={applyFilters}>
            <Search className="h-4 w-4" />
            Search
          </Button>
          <Button variant="outline" onClick={resetFilters}>
            Reset
          </Button>
        </div>
      </div>
    );
  }

  return (
    <>
      <section className="container py-10">
        <div className="mb-8 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="eyebrow mb-4">Research shelf</div>
            <h1 className="font-serif text-5xl font-semibold tracking-tight text-foreground">
              Browse, read, and study your ingested papers.
            </h1>
            <p className="mt-4 text-lg leading-8 text-muted-foreground">
              This workspace mirrors the Streamlit prototype while adding a more
              deliberate reading environment for PDFs, mind maps, and flashcard
              review.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Badge>{papersQuery.data?.total ?? 0} indexed papers</Badge>
            <Badge variant="muted">{bookmarks.length} saved bookmarks</Badge>
            <Sheet>
              <SheetTrigger asChild className="lg:hidden">
                <Button variant="outline">
                  <Filter className="h-4 w-4" />
                  Filters
                </Button>
              </SheetTrigger>
              <SheetContent side="right">
                <div className="space-y-2">
                  <h2 className="font-serif text-3xl font-semibold">
                    Search & Filters
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Adjust the same search controls from the prototype,
                    optimized for mobile.
                  </p>
                </div>
                {renderFilters()}
              </SheetContent>
            </Sheet>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="hidden lg:block">
            <Card className="sticky top-28">
              <CardHeader>
                <CardTitle>Search & Filters</CardTitle>
                <CardDescription>
                  Start with the newest papers, then narrow by category or PDF
                  processing status.
                </CardDescription>
              </CardHeader>
              <CardContent>{renderFilters()}</CardContent>
            </Card>
          </aside>

          <div className="space-y-6">
            <Card className="overflow-hidden">
              <CardContent className="flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => setActiveTab("all")}
                    className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                      activeTab === "all"
                        ? "bg-white/10 text-white"
                        : "bg-white/5 text-white/62"
                    }`}
                  >
                    All Papers
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab("bookmarked")}
                    className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                      activeTab === "bookmarked"
                        ? "bg-white/10 text-white"
                        : "bg-white/5 text-white/62"
                    }`}
                  >
                    Bookmarked
                  </button>
                </div>
                <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
                  <span className="inline-flex items-center gap-2">
                    <LibraryBig className="h-4 w-4" />
                    {visiblePapers.length} visible
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <BookOpenText className="h-4 w-4" />
                    PDF preview, mind maps, and study cards
                  </span>
                </div>
              </CardContent>
            </Card>

            {papersQuery.isLoading ? (
              <div className="grid gap-6 xl:grid-cols-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <Card key={index}>
                    <CardContent className="space-y-4 p-6">
                      <Skeleton className="h-4 w-24" />
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-20 w-full rounded-[24px]" />
                      <Skeleton className="h-4 w-3/4" />
                      <div className="grid grid-cols-2 gap-3">
                        <Skeleton className="h-11 rounded-full" />
                        <Skeleton className="h-11 rounded-full" />
                        <Skeleton className="h-11 rounded-full" />
                        <Skeleton className="h-11 rounded-full" />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : papersQuery.isError ? (
              <Card>
                <CardContent className="p-8 text-center">
                  <p className="text-lg font-medium text-foreground">
                    Unable to load papers.
                  </p>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {papersQuery.error instanceof Error
                      ? papersQuery.error.message
                      : "Unexpected error"}
                  </p>
                </CardContent>
              </Card>
            ) : visiblePapers.length ? (
              <div className="space-y-4">
                {deleteError ? (
                  <Card>
                    <CardContent className="p-4 text-sm text-rose-200">
                      {deleteError}
                    </CardContent>
                  </Card>
                ) : null}
                <motion.div layout className="grid gap-6 xl:grid-cols-2">
                  <AnimatePresence>
                    {visiblePapers.map((paper) => (
                      <PaperCard
                        key={paper.id}
                        paper={paper}
                        bookmarked={bookmarks.includes(paper.id)}
                        onToggleBookmark={(paperId) =>
                          setBookmarks((current) =>
                            toggleBookmark(current, paperId),
                          )
                        }
                        onOpenPdf={setPdfPaper}
                        onOpenMindMap={setMindMapPaper}
                        onOpenFlashcards={setFlashcardPaper}
                        onAddToProject={setProjectPickerPaper}
                        onDeletePaper={handleDeletePaper}
                        deletePending={
                          deletePaperMutation.isPending &&
                          deletePaperMutation.variables === paper.id
                        }
                      />
                    ))}
                  </AnimatePresence>
                </motion.div>
              </div>
            ) : (
              <Card>
                <CardContent className="flex flex-col items-center justify-center gap-4 p-10 text-center">
                  <Sparkles className="h-10 w-10 text-paper-500" />
                  <p className="font-serif text-3xl font-semibold">
                    No papers to show.
                  </p>
                  <p className="max-w-lg text-sm leading-6 text-muted-foreground">
                    Try widening your filters, or switch back to All Papers if
                    the current bookmarked view is empty for this search.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </section>

      <PdfDialog
        paper={pdfPaper}
        open={Boolean(pdfPaper)}
        onOpenChange={(open) => !open && setPdfPaper(null)}
      />
      <MindMapDialog
        paper={mindMapPaper}
        open={Boolean(mindMapPaper)}
        onOpenChange={(open) => !open && setMindMapPaper(null)}
      />
      <FlashcardDialog
        paper={flashcardPaper}
        open={Boolean(flashcardPaper)}
        onOpenChange={(open) => !open && setFlashcardPaper(null)}
      />
      <ProjectPickerDialog
        paper={projectPickerPaper}
        open={Boolean(projectPickerPaper)}
        onOpenChange={(open) => !open && setProjectPickerPaper(null)}
      />
    </>
  );
}
