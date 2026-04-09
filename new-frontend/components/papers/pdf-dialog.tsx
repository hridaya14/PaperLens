"use client";

import type { Paper } from "@/lib/schemas";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type PdfDialogProps = {
  paper: Paper | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function PdfDialog({ paper, open, onOpenChange }: PdfDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[92vh] max-w-6xl overflow-hidden p-0">
        {paper ? (
          <>
            <DialogHeader className="border-b border-border px-8 py-6">
              <DialogTitle>{paper.title}</DialogTitle>
              <DialogDescription>
                Embedded from arXiv for quick reading without leaving the
                PaperLens workspace.
              </DialogDescription>
            </DialogHeader>
            {paper.pdf_url?.startsWith("http") ? (
              <iframe
                title={`${paper.title} PDF preview`}
                src={paper.pdf_url}
                className="h-full min-h-[75vh] w-full bg-white"
              />
            ) : (
              <div className="flex h-full min-h-[75vh] w-full flex-col items-center justify-center gap-3 bg-white/5 px-8 text-center text-sm text-muted-foreground">
                <span>PDF previews are only available for hosted URLs.</span>
                <span className="break-all text-white">{paper.pdf_url}</span>
              </div>
            )}
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
