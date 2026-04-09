"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  RefreshCw,
  Trash2,
  UploadCloud,
} from "lucide-react";
import {
  deleteUploadedPaper,
  getUploadStatus,
  getUploadedPaper,
  uploadPaper,
} from "@/lib/api/client";
import type {
  UploadAcceptedResponse,
  UploadedPaperResponse,
  UploadStatusResponse,
} from "@/lib/schemas";
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
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

type UploadMetadataDraft = {
  title: string;
  authors: string;
  categories: string;
  abstract: string;
  publishedDate: string;
};

type UploadTask = {
  taskId: string;
  accepted: UploadAcceptedResponse;
  fileName: string;
  fileSize: number;
  createdAt: string;
  status?: UploadStatusResponse;
  paper?: UploadedPaperResponse | null;
  error?: string | null;
  deleted?: boolean;
};

const defaultMetadata: UploadMetadataDraft = {
  title: "",
  authors: "",
  categories: "",
  abstract: "",
  publishedDate: "",
};

export function UploadWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [metadata, setMetadata] =
    useState<UploadMetadataDraft>(defaultMetadata);
  const [submitting, setSubmitting] = useState(false);
  const [autoPoll, setAutoPoll] = useState(true);
  const [uploads, setUploads] = useState<UploadTask[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [pollingTaskId, setPollingTaskId] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeTask = useMemo(
    () => uploads.find((task) => task.taskId === activeTaskId) ?? null,
    [uploads, activeTaskId],
  );

  useEffect(() => {
    setDeleteConfirm(false);
    setDeleting(false);
  }, [activeTaskId]);

  const handleUpload = useCallback(async () => {
    if (!file) {
      setError("Choose a PDF file to upload.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const metadataPayload: Record<string, unknown> = {};
      if (metadata.title.trim()) {
        metadataPayload.title = metadata.title.trim();
      }
      if (metadata.authors.trim()) {
        metadataPayload.authors = metadata.authors
          .split(",")
          .map((author) => author.trim())
          .filter(Boolean);
      }
      if (metadata.categories.trim()) {
        metadataPayload.categories = metadata.categories
          .split(",")
          .map((category) => category.trim())
          .filter(Boolean);
      }
      if (metadata.abstract.trim()) {
        metadataPayload.abstract = metadata.abstract.trim();
      }
      if (metadata.publishedDate) {
        const date = new Date(`${metadata.publishedDate}T00:00:00`);
        if (!Number.isNaN(date.getTime())) {
          metadataPayload.published_date = date.toISOString();
        }
      }

      if (Object.keys(metadataPayload).length > 0) {
        formData.append("metadata", JSON.stringify(metadataPayload));
      }

      const response = await uploadPaper(formData);
      const newTask: UploadTask = {
        taskId: response.task_id,
        accepted: response,
        fileName: file.name,
        fileSize: file.size,
        createdAt: new Date().toISOString(),
        status: undefined,
        paper: null,
        error: null,
      };

      setUploads((current) => [newTask, ...current]);
      setActiveTaskId(newTask.taskId);
      setFile(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }, [file, metadata]);

  const pollTask = useCallback(async (taskId: string) => {
    setPollingTaskId(taskId);
    setError(null);

    try {
      const latest = await getUploadStatus(taskId);

      setUploads((current) =>
        current.map((task) =>
          task.taskId === taskId
            ? {
                ...task,
                status: latest,
                error: null,
              }
            : task,
        ),
      );

      if (latest.status === "completed" && latest.paper_id) {
        const paper = await getUploadedPaper(latest.paper_id);
        setUploads((current) =>
          current.map((task) =>
            task.taskId === taskId
              ? {
                  ...task,
                  paper,
                }
              : task,
          ),
        );
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to poll status";
      setUploads((current) =>
        current.map((task) =>
          task.taskId === taskId
            ? {
                ...task,
                error: message,
              }
            : task,
        ),
      );
      setError(message);
    } finally {
      setPollingTaskId(null);
    }
  }, []);

  const pollAllActive = useCallback(async () => {
    const tasksToPoll = uploads.filter((task) => {
      if (task.deleted) {
        return false;
      }
      const status = task.status?.status;
      return status !== "completed" && status !== "failed";
    });

    if (tasksToPoll.length === 0) {
      return;
    }

    await Promise.all(tasksToPoll.map((task) => pollTask(task.taskId)));
  }, [uploads, pollTask]);

  useEffect(() => {
    if (!autoPoll || uploads.length === 0) {
      return;
    }

    pollAllActive();
    const timer = setInterval(() => {
      pollAllActive();
    }, 4500);

    return () => clearInterval(timer);
  }, [autoPoll, uploads.length, pollAllActive]);

  const handleDelete = useCallback(async () => {
    if (!activeTask?.paper?.id) {
      setError("No uploaded paper is available to delete.");
      return;
    }

    if (!deleteConfirm) {
      setError("Enable delete confirmation before deleting.");
      return;
    }

    setDeleting(true);
    setError(null);

    try {
      await deleteUploadedPaper(activeTask.paper.id);
      setUploads((current) =>
        current.map((task) =>
          task.taskId === activeTask.taskId
            ? { ...task, paper: null, deleted: true }
            : task,
        ),
      );
      setDeleteConfirm(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Delete request failed";
      setError(message);
    } finally {
      setDeleting(false);
    }
  }, [activeTask, deleteConfirm]);

  function resetForm() {
    setFile(null);
    setMetadata(defaultMetadata);
    setError(null);
  }

  function formatBytes(size: number) {
    if (size < 1024) return `${size} B`;
    const kb = size / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    const mb = kb / 1024;
    return `${mb.toFixed(1)} MB`;
  }

  function statusTone(task: UploadTask) {
    if (task.deleted) return "muted";
    const status = task.status?.status;
    if (status === "completed") return "success";
    if (status === "failed") return "danger";
    if (status === "processing") return "default";
    return "muted";
  }

  function statusLabel(task: UploadTask) {
    if (task.deleted) return "DELETED";
    if (!task.status) return "PENDING";
    return task.status.status.toUpperCase();
  }

  function progressLabel(task: UploadTask) {
    if (!task.status?.progress) return null;
    const step = (task.status.progress as Record<string, unknown>).step;
    return typeof step === "string" ? step.replaceAll("_", " ") : null;
  }

  function StatusIcon(task: UploadTask) {
    if (task.deleted) {
      return <Trash2 className="h-4 w-4 text-rose-200" />;
    }
    if (task.status?.status === "completed") {
      return <CheckCircle2 className="h-4 w-4 text-emerald-300" />;
    }
    if (task.status?.status === "failed") {
      return <AlertTriangle className="h-4 w-4 text-rose-300" />;
    }
    if (task.status?.status === "processing") {
      return <RefreshCw className="h-4 w-4 animate-spin text-amber-200" />;
    }
    return <Clock className="h-4 w-4 text-white/60" />;
  }

  return (
    <section className="container py-10">
      <div className="mb-8 flex flex-col gap-4">
        <div className="eyebrow">Upload validation</div>
        <h1 className="font-serif text-5xl font-semibold tracking-tight text-foreground">
          Test the PDF upload pipeline.
        </h1>
        <p className="max-w-3xl text-lg leading-8 text-muted-foreground">
          Upload multiple PDFs, keep them queued, and watch each task progress.
          This mirrors NotebookLM-style flows where you can keep adding sources
          while earlier ones are still processing.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <Card>
          <CardHeader>
            <CardTitle>Upload a PDF</CardTitle>
            <CardDescription>
              Files must be PDFs under 20MB. Metadata is optional and sent as
              JSON in the multipart body.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="upload-file">PDF file</Label>
              <Input
                id="upload-file"
                type="file"
                accept="application/pdf"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              {file ? (
                <p className="text-sm text-muted-foreground">
                  Selected: {file.name} ({formatBytes(file.size)})
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No file selected yet.
                </p>
              )}
            </div>

            <Separator />

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="upload-title">Title</Label>
                <Input
                  id="upload-title"
                  placeholder="Optional override title"
                  value={metadata.title}
                  onChange={(event) =>
                    setMetadata((current) => ({
                      ...current,
                      title: event.target.value,
                    }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="upload-date">Published date</Label>
                <Input
                  id="upload-date"
                  type="date"
                  value={metadata.publishedDate}
                  onChange={(event) =>
                    setMetadata((current) => ({
                      ...current,
                      publishedDate: event.target.value,
                    }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="upload-authors">Authors</Label>
                <Input
                  id="upload-authors"
                  placeholder="Comma-separated"
                  value={metadata.authors}
                  onChange={(event) =>
                    setMetadata((current) => ({
                      ...current,
                      authors: event.target.value,
                    }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="upload-categories">Categories</Label>
                <Input
                  id="upload-categories"
                  placeholder="Comma-separated tags"
                  value={metadata.categories}
                  onChange={(event) =>
                    setMetadata((current) => ({
                      ...current,
                      categories: event.target.value,
                    }))
                  }
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="upload-abstract">Abstract</Label>
              <Textarea
                id="upload-abstract"
                placeholder="Optional abstract snippet"
                value={metadata.abstract}
                onChange={(event) =>
                  setMetadata((current) => ({
                    ...current,
                    abstract: event.target.value,
                  }))
                }
              />
            </div>

            <div className="flex flex-wrap gap-3">
              <Button onClick={handleUpload} disabled={submitting}>
                <UploadCloud className="h-4 w-4" />
                {submitting ? "Uploading..." : "Add to queue"}
              </Button>
              <Button variant="outline" onClick={resetForm}>
                Clear form
              </Button>
            </div>

            {error ? (
              <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 p-4 text-sm text-rose-200">
                <div className="mb-2 flex items-center gap-2 font-semibold">
                  <AlertTriangle className="h-4 w-4" />
                  Upload error
                </div>
                {error}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Upload queue</CardTitle>
              <CardDescription>
                Keep adding sources while earlier uploads are processing.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {uploads.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-5 text-sm text-muted-foreground">
                  Uploads will appear here with live status updates.
                </div>
              ) : (
                <div className="space-y-3">
                  {uploads.map((task) => {
                    const active = task.taskId === activeTaskId;
                    return (
                      <button
                        key={task.taskId}
                        type="button"
                        onClick={() => setActiveTaskId(task.taskId)}
                        className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                          active
                            ? "border-amber-300/30 bg-amber-300/10"
                            : "border-white/10 bg-white/5 hover:bg-white/8"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            {StatusIcon(task)}
                            <div>
                              <div className="font-medium text-white">
                                {task.fileName}
                              </div>
                              <div className="text-xs text-white/60">
                                {formatBytes(task.fileSize)} •{" "}
                                {new Date(task.createdAt).toLocaleTimeString()}
                              </div>
                            </div>
                          </div>
                          <Badge variant={statusTone(task)}>
                            {statusLabel(task)}
                          </Badge>
                        </div>
                        {progressLabel(task) ? (
                          <div className="mt-2 text-xs capitalize text-white/70">
                            Current step: {progressLabel(task)}
                          </div>
                        ) : null}
                        {task.error ? (
                          <div className="mt-2 text-xs text-rose-200">
                            {task.error}
                          </div>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <Switch checked={autoPoll} onCheckedChange={setAutoPoll} />
                  <span className="text-sm text-muted-foreground">
                    Auto-poll every 4.5s
                  </span>
                </div>
                <Button
                  variant="outline"
                  onClick={pollAllActive}
                  disabled={uploads.length === 0}
                >
                  <RefreshCw className="h-4 w-4" />
                  Poll active tasks
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Selected task detail</CardTitle>
              <CardDescription>
                Inspect status updates and the final paper detail for the
                selected upload.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {activeTask ? (
                <>
                  <div className="flex flex-wrap items-center gap-3">
                    <Badge variant={statusTone(activeTask)}>
                      {statusLabel(activeTask)}
                    </Badge>
                    <Badge variant="dark">Task ID: {activeTask.taskId}</Badge>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
                    <div className="mb-2 flex items-center gap-2 text-white">
                      <FileText className="h-4 w-4" />
                      Progress
                    </div>
                    {progressLabel(activeTask) ? (
                      <span className="capitalize">
                        Current step: {progressLabel(activeTask)}
                      </span>
                    ) : (
                      <span>No progress data yet.</span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="text-xs text-white/60">
                      Created: {new Date(activeTask.createdAt).toLocaleString()}
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => pollTask(activeTask.taskId)}
                      disabled={pollingTaskId === activeTask.taskId}
                    >
                      <RefreshCw className="h-4 w-4" />
                      {pollingTaskId === activeTask.taskId
                        ? "Polling..."
                        : "Poll now"}
                    </Button>
                  </div>

                  {activeTask.paper ? (
                    <>
                      <Separator />
                      <div>
                        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
                          Paper detail
                        </p>
                        <p className="mt-2 font-serif text-2xl text-white">
                          {activeTask.paper.title}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {activeTask.paper.categories.length > 0 ? (
                          activeTask.paper.categories.map((category) => (
                            <Badge key={category} variant="muted">
                              {category}
                            </Badge>
                          ))
                        ) : (
                          <Badge variant="muted">No categories</Badge>
                        )}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        Authors:{" "}
                        {activeTask.paper.authors.length
                          ? activeTask.paper.authors.join(", ")
                          : "Not provided"}
                      </div>
                      <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white/80">
                        {activeTask.paper.abstract ||
                          "No abstract available yet."}
                      </div>
                      <div className="grid gap-3 text-sm text-muted-foreground sm:grid-cols-2">
                        <div>
                          PDF processed:{" "}
                          {activeTask.paper.pdf_processed ? "Yes" : "No"}
                        </div>
                        <div>
                          Chunks indexed:{" "}
                          {activeTask.paper.chunks_indexed ?? "—"}
                        </div>
                        <div>Parser: {activeTask.paper.parser_used ?? "—"}</div>
                        <div>Source: {activeTask.paper.source}</div>
                      </div>
                      <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 p-4 text-sm text-rose-100">
                        <div className="mb-2 flex items-center gap-2 font-semibold">
                          <AlertTriangle className="h-4 w-4" />
                          Danger zone
                        </div>
                        <div className="flex flex-wrap items-center gap-3">
                          <Switch
                            checked={deleteConfirm}
                            onCheckedChange={setDeleteConfirm}
                          />
                          <span className="text-sm text-rose-100/80">
                            Confirm delete
                          </span>
                          <Button
                            variant="outline"
                            className="border-rose-400/40 text-rose-200 hover:bg-rose-500/10"
                            onClick={handleDelete}
                            disabled={!deleteConfirm || deleting}
                          >
                            {deleting ? "Deleting..." : "Delete paper"}
                          </Button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-5 text-sm text-muted-foreground">
                      The paper detail will appear here after the upload
                      pipeline finishes.
                    </div>
                  )}
                </>
              ) : (
                <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-5 text-sm text-muted-foreground">
                  Select an upload from the queue to view its details.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
