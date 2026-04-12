"use client";

import {
  Bookmark,
  BrainCircuit,
  FileText,
  FolderPlus,
  Layers3,
  Trash2,
} from "lucide-react";
import { motion } from "framer-motion";
import type { Paper } from "@/lib/schemas";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate, truncateText } from "@/lib/utils";

type PaperCardProps = {
  paper: Paper;
  bookmarked: boolean;
  onToggleBookmark: (paperId: string) => void;
  onOpenPdf: (paper: Paper) => void;
  onOpenMindMap: (paper: Paper) => void;
  onOpenFlashcards: (paper: Paper) => void;
  onAddToProject: (paper: Paper) => void;
  onDeletePaper: (paper: Paper) => void;
  deletePending?: boolean;
};

export function PaperCard({
  paper,
  bookmarked,
  onToggleBookmark,
  onOpenPdf,
  onOpenMindMap,
  onOpenFlashcards,
  onAddToProject,
  onDeletePaper,
  deletePending = false,
}: PaperCardProps) {
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      className="group panel-surface flex h-full flex-col overflow-hidden border-white/10 bg-[linear-gradient(180deg,rgba(19,27,25,0.96),rgba(15,21,19,0.94))] p-6"
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-200/80">{formatDate(paper.published_date)}</p>
          <h3 className="font-serif text-2xl font-semibold leading-tight text-white">{paper.title}</h3>
        </div>
        <button
          type="button"
          onClick={() => onToggleBookmark(paper.id)}
          className="rounded-full border border-white/10 bg-white/6 p-3 text-white/60 transition hover:bg-white/10 hover:text-white"
          aria-label={bookmarked ? "Remove bookmark" : "Add bookmark"}
        >
          <Bookmark className={`h-4 w-4 ${bookmarked ? "fill-current text-amber-200" : ""}`} />
        </button>
      </div>

      <p className="mb-4 text-sm leading-6 text-white/68">
        {paper.authors.length ? paper.authors.slice(0, 3).join(", ") : "No authors listed"}
        {paper.authors.length > 3 ? "..." : ""}
      </p>

      <div className="mb-5 rounded-[24px] border border-white/10 bg-white/5 p-4 text-sm leading-6 text-white/72">
        {truncateText(paper.abstract || "No abstract available", 260)}
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Badge variant={paper.pdf_processed ? "success" : "muted"}>
          {paper.pdf_processed ? "Processed" : "Processing"}
        </Badge>
        {paper.categories.slice(0, 4).map((category) => (
          <Badge key={category} variant="muted">
            {category}
          </Badge>
        ))}
      </div>

      <div className="mt-auto grid grid-cols-2 gap-3">
        <Button variant="outline" onClick={() => onOpenPdf(paper)}>
          <FileText className="h-4 w-4" />
          PDF
        </Button>
        <Button variant="outline" onClick={() => onOpenMindMap(paper)}>
          <BrainCircuit className="h-4 w-4" />
          Mind Map
        </Button>
        <Button variant="outline" onClick={() => onOpenFlashcards(paper)}>
          <Layers3 className="h-4 w-4" />
          Flashcards
        </Button>
        <Button variant="outline" onClick={() => onAddToProject(paper)}>
          <FolderPlus className="h-4 w-4" />
          Add to Project
        </Button>
        <Button
          variant="danger"
          onClick={() => onDeletePaper(paper)}
          disabled={deletePending}
        >
          <Trash2 className="h-4 w-4" />
          {deletePending ? "Deleting..." : "Delete"}
        </Button>
        <div className="col-span-2 flex items-center justify-end text-sm text-white/55">
          {bookmarked ? "Bookmarked" : "Saved locally"}
        </div>
      </div>
    </motion.article>
  );
}
