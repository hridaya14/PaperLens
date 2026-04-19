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
                Embedded for quick reading without leaving the PaperLens
                workspace.
              </DialogDescription>
            </DialogHeader>
            {paper.pdf_url?.startsWith("http") ? (
              <iframe
                title={`${paper.title} PDF preview`}
                src={paper.pdf_url}
                className="h-full min-h-[75vh] w-full bg-white"
              />
            ) : (
              <iframe
                title={`${paper.title} PDF preview`}
                src={`/api/papers/${paper.id}/pdf`}
                className="h-full min-h-[75vh] w-full bg-white"
              />
            )}
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
