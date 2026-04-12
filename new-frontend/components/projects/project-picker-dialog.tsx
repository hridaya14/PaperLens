"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderPlus, Plus, Sparkles } from "lucide-react";
import {
  addPaperToProject,
  createProject,
  listProjects,
} from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type ProjectPickerDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paper: {
    id: string;
    title: string;
  } | null;
};

export function ProjectPickerDialog({
  open,
  onOpenChange,
  paper,
}: ProjectPickerDialogProps) {
  const queryClient = useQueryClient();
  const projectsQuery = useQuery({
    queryKey: ["projects", "list"],
    queryFn: listProjects,
    enabled: open,
  });
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [addedProjectIds, setAddedProjectIds] = useState<string[]>([]);

  useEffect(() => {
    if (!open) {
      setNewProjectName("");
      setNewProjectDescription("");
      setStatusMessage(null);
      setErrorMessage(null);
      setAddedProjectIds([]);
    }
  }, [open]);

  const addSourceMutation = useMutation({
    mutationFn: async (projectId: string) => {
      if (!paper) {
        throw new Error("Choose a paper before adding it to a project.");
      }

      return addPaperToProject(projectId, paper.id);
    },
    onSuccess: (_, projectId) => {
      const projectName =
        projectsQuery.data?.find((project) => project.id === projectId)?.name ??
        "project";

      setAddedProjectIds((current) =>
        current.includes(projectId) ? current : [...current, projectId],
      );
      setStatusMessage(`Added "${paper?.title}" to ${projectName}.`);
      setErrorMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error, projectId) => {
      const message =
        error instanceof Error ? error.message : "Unable to update project";

      if (message.toLowerCase().includes("already in this project")) {
        setAddedProjectIds((current) =>
          current.includes(projectId) ? current : [...current, projectId],
        );
        setStatusMessage(
          `"${paper?.title}" is already available in that project.`,
        );
        setErrorMessage(null);
        return;
      }

      setErrorMessage(message);
    },
  });

  const createProjectMutation = useMutation({
    mutationFn: async () => {
      const created = await createProject({
        name: newProjectName,
        description: newProjectDescription,
      });

      if (!paper) {
        return created;
      }

      await addPaperToProject(created.id, paper.id);
      return created;
    },
    onSuccess: (project) => {
      setAddedProjectIds((current) =>
        current.includes(project.id) ? current : [...current, project.id],
      );
      setStatusMessage(`Created ${project.name} and added "${paper?.title}".`);
      setErrorMessage(null);
      setNewProjectName("");
      setNewProjectDescription("");
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error) => {
      setErrorMessage(
        error instanceof Error ? error.message : "Unable to create project",
      );
    },
  });

  const orderedProjects = useMemo(
    () => [...(projectsQuery.data ?? [])].sort((left, right) => {
      if (addedProjectIds.includes(left.id) && !addedProjectIds.includes(right.id)) {
        return -1;
      }

      if (!addedProjectIds.includes(left.id) && addedProjectIds.includes(right.id)) {
        return 1;
      }

      return 0;
    }),
    [addedProjectIds, projectsQuery.data],
  );

  const canCreateProject = newProjectName.trim().length > 0 && !createProjectMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Add Paper To Projects</DialogTitle>
          <DialogDescription>
            Choose one or more projects for {paper ? `"${paper.title}"` : "this paper"}.
            Project chats will then scope retrieval to that project&apos;s papers.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-white">Existing projects</p>
                <p className="text-sm text-muted-foreground">
                  Add the paper to one workspace or several.
                </p>
              </div>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70">
                {projectsQuery.data?.length ?? 0} projects
              </span>
            </div>

            {projectsQuery.isLoading ? (
              <div className="rounded-[24px] border border-white/10 bg-white/5 p-5 text-sm text-muted-foreground">
                Loading projects...
              </div>
            ) : orderedProjects.length > 0 ? (
              <div className="space-y-3">
                {orderedProjects.map((project) => {
                  const added = addedProjectIds.includes(project.id);
                  return (
                    <div
                      key={project.id}
                      className={cn(
                        "rounded-[24px] border p-4 transition",
                        added
                          ? "border-emerald-300/25 bg-emerald-400/10"
                          : "border-white/10 bg-white/5",
                      )}
                    >
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="space-y-1">
                          <p className="font-medium text-white">{project.name}</p>
                          <p className="text-sm text-muted-foreground">
                            {project.description?.trim() || "No description yet."}
                          </p>
                          <p className="text-xs uppercase tracking-[0.16em] text-white/45">
                            {project.source_count} sources
                          </p>
                        </div>
                        <Button
                          variant={added ? "secondary" : "outline"}
                          disabled={addSourceMutation.isPending || !paper}
                          onClick={() => addSourceMutation.mutate(project.id)}
                        >
                          {added ? "Added" : "Add paper"}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-[24px] border border-dashed border-white/10 bg-white/5 p-5 text-sm text-muted-foreground">
                No projects yet. Create one on the right and this paper can be added immediately.
              </div>
            )}
          </div>

          <div className="space-y-4 rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(247,192,95,0.12),rgba(255,255,255,0.03))] p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-300 text-graphite-900">
                <FolderPlus className="h-5 w-5" />
              </div>
              <div>
                <p className="font-medium text-white">Create a new project</p>
                <p className="text-sm text-muted-foreground">
                  Useful when a paper kicks off a fresh research thread.
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="new-project-name">Project name</Label>
              <Input
                id="new-project-name"
                value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)}
                placeholder="Multimodal evaluation study"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="new-project-description">Description</Label>
              <Textarea
                id="new-project-description"
                value={newProjectDescription}
                onChange={(event) => setNewProjectDescription(event.target.value)}
                placeholder="Optional context for this project"
                className="min-h-[120px]"
              />
            </div>

            <Button
              className="w-full"
              disabled={!canCreateProject}
              onClick={() => createProjectMutation.mutate()}
            >
              <Plus className="h-4 w-4" />
              {createProjectMutation.isPending
                ? "Creating project..."
                : "Create and add paper"}
            </Button>

            {statusMessage ? (
              <div className="rounded-2xl border border-emerald-300/15 bg-emerald-400/10 p-4 text-sm text-emerald-100">
                <div className="mb-2 flex items-center gap-2 font-medium">
                  <Sparkles className="h-4 w-4" />
                  Project updated
                </div>
                {statusMessage}
              </div>
            ) : null}

            {errorMessage ? (
              <div className="rounded-2xl border border-rose-400/15 bg-rose-500/10 p-4 text-sm text-rose-100">
                {errorMessage}
              </div>
            ) : null}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
