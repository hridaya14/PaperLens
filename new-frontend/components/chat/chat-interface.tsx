"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  Cpu,
  FolderKanban,
  FolderPlus,
  PanelLeft,
  PauseCircle,
  Plus,
  SendHorizonal,
  Sparkles,
  Trash2,
  User2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { AVAILABLE_CATEGORIES, CHAT_MODELS } from "@/lib/constants";
import {
  askChatSession,
  askProjectChat,
  clearChatSession,
  clearProjectChat,
  createChatSession,
  createProject,
  deleteChatSession,
  deleteProject,
  getChatSession,
  getProject,
  getProjectChat,
  listChatSessions,
  listProjects,
  removePaperFromProject,
  streamChatSession,
  streamProjectChat,
} from "@/lib/api/client";
import type {
  ChatRequest,
  StreamChunkEvent,
  ChatSession as ChatSessionSummary,
  ProjectSummary,
} from "@/lib/schemas";
import { readChatStream } from "@/lib/stream";
import { cn, formatDate, truncateText } from "@/lib/utils";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

type WorkspaceSelection =
  | { type: "session"; id: string | null }
  | { type: "project"; id: string };

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  chunksUsed?: number;
  searchMode?: string;
  status?: "streaming" | "complete" | "error";
};

const defaultSettings: Omit<ChatRequest, "query"> = {
  top_k: 3,
  use_hybrid: true,
  model: CHAT_MODELS[0],
  categories: null,
};

export function ChatInterface() {
  const queryClient = useQueryClient();
  const abortControllerRef = useRef<AbortController | null>(null);
  const scrollViewportRef = useRef<HTMLDivElement | null>(null);
  const initializedWorkspaceRef = useRef(false);
  const [settings, setSettings] = useState(defaultSettings);
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceSelection>({
    type: "session",
    id: null,
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");

  const sessionsQuery = useQuery({
    queryKey: ["chat", "sessions"],
    queryFn: listChatSessions,
  });
  const projectsQuery = useQuery({
    queryKey: ["projects", "list"],
    queryFn: listProjects,
  });

  const activeSessionId =
    activeWorkspace.type === "session" ? activeWorkspace.id : null;
  const activeProjectId =
    activeWorkspace.type === "project" ? activeWorkspace.id : null;

  const activeSessionQuery = useQuery({
    queryKey: ["chat", "session", activeSessionId],
    queryFn: () => getChatSession(activeSessionId as string),
    enabled: activeWorkspace.type === "session" && Boolean(activeSessionId),
  });
  const activeProjectQuery = useQuery({
    queryKey: ["projects", "detail", activeProjectId],
    queryFn: () => getProject(activeProjectId as string),
    enabled: activeWorkspace.type === "project" && Boolean(activeProjectId),
  });
  const activeProjectChatQuery = useQuery({
    queryKey: ["projects", "chat", activeProjectId],
    queryFn: () => getProjectChat(activeProjectId as string),
    enabled: activeWorkspace.type === "project" && Boolean(activeProjectId),
  });

  const createProjectMutation = useMutation({
    mutationFn: () =>
      createProject({
        name: newProjectName,
        description: newProjectDescription,
      }),
    onSuccess: async (project) => {
      setProjectDialogOpen(false);
      setNewProjectName("");
      setNewProjectDescription("");
      setWorkspaceError(null);
      setActiveWorkspace({ type: "project", id: project.id });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error) => {
      setWorkspaceError(
        error instanceof Error ? error.message : "Unable to create project",
      );
    },
  });

  const removeSourceMutation = useMutation({
    mutationFn: ({
      projectId,
      paperId,
    }: {
      projectId: string;
      paperId: string;
    }) => removePaperFromProject(projectId, paperId),
    onSuccess: async (_, variables) => {
      setWorkspaceError(null);
      await queryClient.invalidateQueries({
        queryKey: ["projects", "detail", variables.projectId],
      });
      await queryClient.invalidateQueries({ queryKey: ["projects", "list"] });
    },
    onError: (error) => {
      setWorkspaceError(
        error instanceof Error ? error.message : "Unable to remove source",
      );
    },
  });

  const activeSessionSummary = useMemo(
    () =>
      sessionsQuery.data?.find((session) => session.id === activeSessionId) ??
      null,
    [activeSessionId, sessionsQuery.data],
  );
  const activeProjectSummary = useMemo(
    () =>
      projectsQuery.data?.find((project) => project.id === activeProjectId) ??
      null,
    [activeProjectId, projectsQuery.data],
  );
  const activeProject = activeProjectQuery.data ?? null;
  const activeWorkspaceKey =
    activeWorkspace.type === "session"
      ? `session:${activeWorkspace.id ?? "draft"}`
      : `project:${activeWorkspace.id}`;
  const activeWorkspaceTitle =
    activeWorkspace.type === "project"
      ? activeProject?.name ?? activeProjectSummary?.name ?? "Project"
      : activeSessionQuery.data?.title ??
        activeSessionSummary?.title ??
        (activeWorkspace.id ? "Untitled chat" : "New chat");
  const activeWorkspaceSubtitle =
    activeWorkspace.type === "project"
      ? activeProject?.description?.trim() ||
        "Scoped retrieval across this project's selected papers."
      : activeWorkspace.id
        ? "Persistent general chat across your full indexed library."
        : "Start a new general conversation and it will be saved after the first message.";
  const activeMessagesLoading =
    activeWorkspace.type === "project"
      ? activeProjectQuery.isLoading || activeProjectChatQuery.isLoading
      : Boolean(activeSessionId) && activeSessionQuery.isLoading;

  useEffect(() => {
    const viewport = scrollViewportRef.current;
    if (!viewport) {
      return;
    }

    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (
      initializedWorkspaceRef.current ||
      sessionsQuery.isLoading ||
      projectsQuery.isLoading
    ) {
      return;
    }

    initializedWorkspaceRef.current = true;

    if ((sessionsQuery.data?.length ?? 0) > 0) {
      setActiveWorkspace({ type: "session", id: sessionsQuery.data?.[0]?.id ?? null });
    }
  }, [
    projectsQuery.isLoading,
    sessionsQuery.data,
    sessionsQuery.isLoading,
  ]);

  useEffect(() => {
    if (isStreaming) {
      return;
    }

    if (activeWorkspace.type === "session") {
      if (!activeSessionId) {
        setMessages([]);
        return;
      }

      if (activeSessionQuery.data) {
        setMessages(
          activeSessionQuery.data.messages.map((message) => ({
            id: message.id,
            role: message.role,
            content: message.content,
            status: "complete",
          })),
        );
      }

      return;
    }

    if (activeProjectChatQuery.data) {
      setMessages(
        activeProjectChatQuery.data.messages.map((message) => ({
          id: message.id,
          role: message.role,
          content: message.content,
          status: "complete",
        })),
      );
    }
  }, [
    activeProjectChatQuery.data,
    activeSessionId,
    activeSessionQuery.data,
    activeWorkspaceKey,
    activeWorkspace.type,
    isStreaming,
  ]);

  const handleSelectSession = (sessionId: string | null) => {
    stopStreaming();
    setWorkspaceError(null);
    setActiveWorkspace({ type: "session", id: sessionId });
    setSidebarOpen(false);
  };

  const handleSelectProject = (projectId: string) => {
    stopStreaming();
    setWorkspaceError(null);
    setActiveWorkspace({ type: "project", id: projectId });
    setSidebarOpen(false);
  };

  async function handleSubmit() {
    const trimmed = query.trim();
    if (!trimmed || isStreaming) {
      return;
    }

    setWorkspaceError(null);

    if (
      activeWorkspace.type === "project" &&
      (activeProject?.sources.length ?? 0) === 0
    ) {
      setWorkspaceError(
        "This project has no papers yet. Add sources from Papers or Uploads before asking project-scoped questions.",
      );
      return;
    }

    let workingWorkspace = activeWorkspace;

    if (workingWorkspace.type === "session" && !workingWorkspace.id) {
      try {
        const createdSession = await createChatSession();
        workingWorkspace = { type: "session", id: createdSession.id };
        setActiveWorkspace(workingWorkspace);
        await queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
      } catch (error) {
        setWorkspaceError(
          error instanceof Error
            ? error.message
            : "Unable to create a new chat session",
        );
        return;
      }
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      status: "complete",
    };
    const assistantMessageId = crypto.randomUUID();
    const payload: ChatRequest = {
      query: trimmed,
      top_k: settings.top_k,
      use_hybrid: settings.use_hybrid,
      model: settings.model,
      categories: settings.categories,
    };

    setMessages((current) => [
      ...current,
      userMessage,
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        sources: [],
        chunksUsed: 0,
        searchMode: "",
        status: "streaming",
      },
    ]);
    setQuery("");
    setIsStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response =
        workingWorkspace.type === "project"
          ? await streamProjectChat(workingWorkspace.id, payload, controller.signal)
          : await streamChatSession(
              workingWorkspace.id as string,
              payload,
              controller.signal,
            );

      await readChatStream(response, {
        onChunk: (event) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? updateAssistantMessage(message, event)
                : message,
            ),
          );
        },
        onComplete: (answer) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: answer,
                    status: "complete",
                  }
                : message,
            ),
          );
        },
      });
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMessageId
              ? {
                  ...message,
                  content: `${message.content}\n\nGeneration stopped.`,
                  status: "error",
                }
              : message,
          ),
        );
      } else {
        try {
          const fallback =
            workingWorkspace.type === "project"
              ? await askProjectChat(workingWorkspace.id, payload)
              : await askChatSession(workingWorkspace.id as string, payload);

          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: fallback.answer,
                    sources: fallback.sources,
                    chunksUsed: fallback.chunks_used,
                    searchMode: fallback.search_mode,
                    status: "complete",
                  }
                : message,
            ),
          );
        } catch (fallbackError) {
          const message =
            fallbackError instanceof Error
              ? fallbackError.message
              : "Unable to generate an answer at this time.";
          setMessages((current) =>
            current.map((chatMessage) =>
              chatMessage.id === assistantMessageId
                ? {
                    ...chatMessage,
                    content: message,
                    status: "error",
                  }
                : chatMessage,
            ),
          );
        }
      }
    } finally {
      await invalidateWorkspaceQueries(
        queryClient,
        workingWorkspace,
      );
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }

  async function handleClearHistory() {
    setWorkspaceError(null);
    stopStreaming();

    try {
      if (activeWorkspace.type === "session") {
        if (!activeWorkspace.id) {
          setMessages([]);
          return;
        }

        await clearChatSession(activeWorkspace.id);
        setMessages([]);
        await invalidateWorkspaceQueries(queryClient, activeWorkspace);
        return;
      }

      await clearProjectChat(activeWorkspace.id);
      setMessages([]);
      await invalidateWorkspaceQueries(queryClient, activeWorkspace);
    } catch (error) {
      setWorkspaceError(
        error instanceof Error ? error.message : "Unable to clear history",
      );
    }
  }

  async function handleDeleteWorkspace() {
    setWorkspaceError(null);
    stopStreaming();

    if (activeWorkspace.type === "session") {
      if (!activeWorkspace.id) {
        setMessages([]);
        return;
      }

      const confirmed = window.confirm(
        `Delete "${activeWorkspaceTitle}"? This will remove the whole chat thread.`,
      );

      if (!confirmed) {
        return;
      }

      try {
        const fallbackSession = sessionsQuery.data?.find(
          (session) => session.id !== activeWorkspace.id,
        );
        await deleteChatSession(activeWorkspace.id);
        setActiveWorkspace(
          fallbackSession
            ? { type: "session", id: fallbackSession.id }
            : { type: "session", id: null },
        );
        setMessages([]);
        await queryClient.invalidateQueries({ queryKey: ["chat"] });
      } catch (error) {
        setWorkspaceError(
          error instanceof Error ? error.message : "Unable to delete chat",
        );
      }

      return;
    }

    const confirmed = window.confirm(
      `Delete project "${activeWorkspaceTitle}"? Sources stay in the library, but the project and its chat will be removed.`,
    );

    if (!confirmed) {
      return;
    }

    try {
      const fallbackSession = sessionsQuery.data?.[0] ?? null;
      await deleteProject(activeWorkspace.id);
      setActiveWorkspace(
        fallbackSession
          ? { type: "session", id: fallbackSession.id }
          : { type: "session", id: null },
      );
      setMessages([]);
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    } catch (error) {
      setWorkspaceError(
        error instanceof Error ? error.message : "Unable to delete project",
      );
    }
  }

  function stopStreaming() {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setIsStreaming(false);
  }

  function renderSidebar() {
    return (
      <div className="space-y-6">
        <div className="space-y-3">
          <Button
            className="w-full justify-center"
            onClick={() => handleSelectSession(null)}
          >
            <Plus className="h-4 w-4" />
            New chat
          </Button>
          <Button
            variant="outline"
            className="w-full justify-center"
            onClick={() => {
              setWorkspaceError(null);
              setProjectDialogOpen(true);
            }}
          >
            <FolderPlus className="h-4 w-4" />
            New project
          </Button>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-[0.2em] text-white/45">
              General chats
            </p>
            <Badge variant="muted">{sessionsQuery.data?.length ?? 0}</Badge>
          </div>

          <button
            type="button"
            onClick={() => handleSelectSession(null)}
            className={cn(
              "w-full rounded-[24px] border px-4 py-3 text-left transition",
              activeWorkspace.type === "session" && activeWorkspace.id === null
                ? "border-amber-300/25 bg-amber-300/12 text-white"
                : "border-white/10 bg-white/5 text-white/75 hover:bg-white/8",
            )}
          >
            <p className="font-medium">New chat draft</p>
            <p className="mt-1 text-xs text-white/55">
              Start fresh against the full library
            </p>
          </button>

          {sessionsQuery.isLoading ? (
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
              Loading chat history...
            </div>
          ) : sessionsQuery.data?.length ? (
            sessionsQuery.data.map((session) => (
              <SidebarSessionButton
                key={session.id}
                active={
                  activeWorkspace.type === "session" &&
                  activeWorkspace.id === session.id
                }
                session={session}
                onSelect={handleSelectSession}
              />
            ))
          ) : (
            <div className="rounded-[24px] border border-dashed border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
              Persistent chats will show up here after the first message.
            </div>
          )}
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-[0.2em] text-white/45">
              Projects
            </p>
            <Badge variant="muted">{projectsQuery.data?.length ?? 0}</Badge>
          </div>

          {projectsQuery.isLoading ? (
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
              Loading projects...
            </div>
          ) : projectsQuery.data?.length ? (
            projectsQuery.data.map((project) => (
              <SidebarProjectButton
                key={project.id}
                active={
                  activeWorkspace.type === "project" &&
                  activeWorkspace.id === project.id
                }
                project={project}
                onSelect={handleSelectProject}
              />
            ))
          ) : (
            <div className="rounded-[24px] border border-dashed border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
              Projects give you a scoped source set and a separate persistent thread.
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <>
      <section className="container py-10">
        <div className="mb-8 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-4xl">
            <div className="eyebrow mb-4">
              {activeWorkspace.type === "project"
                ? "Project assistant"
                : "Persistent research assistant"}
            </div>
            <h1 className="font-serif text-5xl font-semibold tracking-tight">
              {activeWorkspaceTitle}
            </h1>
            <p className="mt-4 text-lg leading-8 text-muted-foreground">
              {activeWorkspaceSubtitle}
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              variant="outline"
              className="xl:hidden"
              onClick={() => setSidebarOpen(true)}
            >
              <PanelLeft className="h-4 w-4" />
              Conversations
            </Button>
            <Badge>
              {activeWorkspace.type === "project"
                ? "Project-scoped retrieval"
                : "General retrieval"}
            </Badge>
            <Badge variant="muted">
              {settings.use_hybrid ? "Hybrid search" : "BM25 mode"}
            </Badge>
            <Badge variant="muted">{settings.top_k} chunks</Badge>
          </div>
        </div>

        <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
          <aside className="hidden xl:block">
            <Card className="sticky top-28 max-h-[calc(100vh-8rem)] overflow-hidden">
              <CardHeader>
                <CardTitle>Workspaces</CardTitle>
                <CardDescription>
                  Switch between general chats and project-specific threads.
                </CardDescription>
              </CardHeader>
              <CardContent className="max-h-[calc(100vh-14rem)] overflow-y-auto pr-2">
                {renderSidebar()}
              </CardContent>
            </Card>
          </aside>

          <div className="space-y-6">
            {workspaceError ? (
              <Card>
                <CardContent className="p-4 text-sm text-rose-200">
                  {workspaceError}
                </CardContent>
              </Card>
            ) : null}

            <Card className="overflow-hidden">
              <CardContent className="p-0">
                <div
                  ref={scrollViewportRef}
                  className="h-[560px] space-y-4 overflow-y-auto p-6"
                >
                  {activeMessagesLoading ? (
                    <div className="flex min-h-[480px] items-center justify-center text-sm text-muted-foreground">
                      Loading conversation...
                    </div>
                  ) : messages.length === 0 ? (
                    <div className="flex min-h-[480px] flex-col items-center justify-center gap-4 text-center">
                      <Sparkles className="h-10 w-10 text-paper-500" />
                      <p className="font-serif text-3xl font-semibold">
                        {activeWorkspace.type === "project"
                          ? "Start a project conversation."
                          : "Start a research conversation."}
                      </p>
                      <p className="max-w-xl text-sm leading-6 text-muted-foreground">
                        {activeWorkspace.type === "project"
                          ? activeProject?.sources.length
                            ? "Ask only across the papers added to this project. The thread stays separate from your general assistant history."
                            : "This project does not have any papers yet. Add sources from the Papers or Uploads workspace, then come back here for scoped RAG."
                          : "Ask about one paper, a cluster of ideas, or trends across the indexed corpus. General chats persist like a standard assistant sidebar."}
                      </p>
                    </div>
                  ) : (
                    <AnimatePresence initial={false}>
                      {messages.map((message) => (
                        <motion.div
                          key={message.id}
                          initial={{ opacity: 0, y: 16 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -16 }}
                          className={`flex gap-4 ${
                            message.role === "assistant" ? "" : "justify-end"
                          }`}
                        >
                          {message.role === "assistant" ? (
                            <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-amber-400 text-graphite-900">
                              <Bot className="h-4 w-4" />
                            </div>
                          ) : null}

                          <div
                            className={`max-w-3xl rounded-[28px] border px-5 py-4 ${
                              message.role === "assistant"
                                ? "border-white/10 bg-white/5 text-white"
                                : "border-amber-300/15 bg-amber-300/12 text-amber-50"
                            }`}
                          >
                            {message.role === "assistant" ? (
                              <div className="prose-markdown">
                                <ReactMarkdown>
                                  {message.content || "Thinking..."}
                                </ReactMarkdown>
                              </div>
                            ) : (
                              <p className="text-sm leading-7">{message.content}</p>
                            )}

                            {message.role === "assistant" ? (
                              <div className="mt-4 space-y-3">
                                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                                  {message.searchMode ? (
                                    <Badge variant="muted">
                                      <Cpu className="mr-1 h-3 w-3" />
                                      {message.searchMode}
                                    </Badge>
                                  ) : null}
                                  {message.chunksUsed ? (
                                    <Badge variant="muted">
                                      {message.chunksUsed} chunks
                                    </Badge>
                                  ) : null}
                                  {message.status === "streaming" ? (
                                    <Badge variant="muted">Streaming</Badge>
                                  ) : null}
                                  {message.status === "error" ? (
                                    <Badge variant="danger">Needs attention</Badge>
                                  ) : null}
                                </div>

                                {message.sources?.length ? (
                                  <Accordion
                                    type="single"
                                    collapsible
                                    className="rounded-[20px] border border-white/10 bg-black/15 px-4"
                                  >
                                    <AccordionItem value="sources" className="border-none">
                                      <AccordionTrigger>Sources</AccordionTrigger>
                                      <AccordionContent>
                                        <ul className="space-y-2 text-sm">
                                          {message.sources.map((source) => (
                                            <li key={source}>
                                              <a
                                                href={source}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-amber-200 underline underline-offset-4"
                                              >
                                                {source}
                                              </a>
                                            </li>
                                          ))}
                                        </ul>
                                      </AccordionContent>
                                    </AccordionItem>
                                  </Accordion>
                                ) : null}
                              </div>
                            ) : null}
                          </div>

                          {message.role === "user" ? (
                            <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-white/8 text-white">
                              <User2 className="h-4 w-4" />
                            </div>
                          ) : null}
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-4 p-6">
                <Label htmlFor="chat-query">
                  {activeWorkspace.type === "project"
                    ? "Ask about this project"
                    : "Ask about your paper library"}
                </Label>
                <Textarea
                  id="chat-query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={
                    activeWorkspace.type === "project"
                      ? "Summarize the main methodologies across this project's sources. Where do they disagree?"
                      : "What problem does this paper solve? How do recent multimodal approaches differ from earlier work?"
                  }
                  onKeyDown={(event) => {
                    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                      event.preventDefault();
                      void handleSubmit();
                    }
                  }}
                  className="min-h-[140px]"
                />
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                    Press Cmd/Ctrl + Enter to send
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <Button variant="outline" onClick={() => void handleClearHistory()}>
                      <Trash2 className="h-4 w-4" />
                      Clear history
                    </Button>
                    {isStreaming ? (
                      <Button variant="danger" onClick={stopStreaming}>
                        <PauseCircle className="h-4 w-4" />
                        Stop
                      </Button>
                    ) : (
                      <Button onClick={() => void handleSubmit()}>
                        <SendHorizonal className="h-4 w-4" />
                        Ask
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>
                  {activeWorkspace.type === "project"
                    ? "Project context"
                    : "Conversation context"}
                </CardTitle>
                <CardDescription>
                  {activeWorkspace.type === "project"
                    ? "Project chats retrieve only from papers added to this workspace."
                    : "General chats search across the full indexed collection."}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-[24px] border border-white/10 bg-white/5 p-4">
                  <p className="font-medium text-white">{activeWorkspaceTitle}</p>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    {activeWorkspaceSubtitle}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {activeWorkspace.type === "project" ? (
                    <>
                      <Badge>{activeProject?.sources.length ?? activeProjectSummary?.source_count ?? 0} sources</Badge>
                      {activeProject?.overview ? (
                        <Badge variant="muted">Overview ready</Badge>
                      ) : (
                        <Badge variant="muted">Overview pending</Badge>
                      )}
                    </>
                  ) : (
                    <>
                      <Badge>{messages.length} loaded messages</Badge>
                      {activeWorkspace.id ? (
                        <Badge variant="muted">
                          Updated {formatDate(activeSessionQuery.data?.updated_at ?? activeSessionSummary?.updated_at)}
                        </Badge>
                      ) : (
                        <Badge variant="muted">Draft mode</Badge>
                      )}
                    </>
                  )}
                </div>

                {activeWorkspace.type === "project" ? (
                  activeProject?.overview ? (
                    <div className="rounded-[24px] border border-white/10 bg-white/5 p-4 text-sm leading-6 text-white/78">
                      {activeProject.overview}
                    </div>
                  ) : (
                    <div className="rounded-[24px] border border-dashed border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
                      This project does not have an overview yet. Once you start curating sources here, this panel can show a higher-level summary.
                    </div>
                  )
                ) : (
                  <div className="rounded-[24px] border border-dashed border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
                    Session titles are derived from the first user message and stay separate from project threads.
                  </div>
                )}

                <Button
                  variant="danger"
                  className="w-full justify-center"
                  onClick={() => void handleDeleteWorkspace()}
                >
                  <Trash2 className="h-4 w-4" />
                  {activeWorkspace.type === "project"
                    ? "Delete project"
                    : activeWorkspace.id
                      ? "Delete chat"
                      : "Discard draft"}
                </Button>
              </CardContent>
            </Card>

            {activeWorkspace.type === "project" ? (
              <Card>
                <CardHeader>
                  <CardTitle>Project sources</CardTitle>
                  <CardDescription>
                    These papers define the retrieval scope for this thread.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {activeProject?.sources.length ? (
                    activeProject.sources.map((source) => (
                      <div
                        key={source.id}
                        className="rounded-[22px] border border-white/10 bg-white/5 p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1">
                            <p className="font-medium text-white">
                              {truncateText(source.title, 90)}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Added {formatDate(source.added_at)}
                            </p>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={
                              removeSourceMutation.isPending &&
                              removeSourceMutation.variables?.paperId === source.id
                            }
                            onClick={() =>
                              removeSourceMutation.mutate({
                                projectId: activeWorkspace.id,
                                paperId: source.id,
                              })
                            }
                          >
                            Remove
                          </Button>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Badge variant={source.pdf_processed ? "success" : "muted"}>
                            {source.pdf_processed ? "Processed" : "Processing"}
                          </Badge>
                          {source.categories.slice(0, 3).map((category) => (
                            <Badge key={category} variant="muted">
                              {category}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-[24px] border border-dashed border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
                      Add papers from the library or uploads workspace to start using this project.
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : null}

            <Card className="h-fit">
              <CardHeader>
                <CardTitle>RAG settings</CardTitle>
                <CardDescription>
                  These map directly to the backend request body for both sessions and projects.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="top-k">Top K chunks</Label>
                    <span className="text-sm text-muted-foreground">
                      {settings.top_k}
                    </span>
                  </div>
                  <Slider
                    id="top-k"
                    min={1}
                    max={10}
                    step={1}
                    value={[settings.top_k]}
                    onValueChange={([value]) =>
                      setSettings((current) => ({ ...current, top_k: value }))
                    }
                  />
                </div>

                <div className="flex items-center justify-between rounded-[24px] border border-white/10 bg-white/5 p-4">
                  <div>
                    <p className="text-sm font-medium">Use hybrid search</p>
                    <p className="text-xs leading-5 text-muted-foreground">
                      Combine BM25 and dense embeddings when available.
                    </p>
                  </div>
                  <Switch
                    checked={settings.use_hybrid}
                    onCheckedChange={(checked) =>
                      setSettings((current) => ({
                        ...current,
                        use_hybrid: checked,
                      }))
                    }
                  />
                </div>

                <label className="space-y-2">
                  <span className="block text-sm font-medium">Model</span>
                  <select
                    value={settings.model}
                    onChange={(event) =>
                      setSettings((current) => ({
                        ...current,
                        model: event.target.value,
                      }))
                    }
                    className="field-surface h-12 w-full appearance-none rounded-2xl px-4 text-sm outline-none focus:ring-2 focus:ring-ring"
                  >
                    {CHAT_MODELS.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="space-y-3">
                  <Label>Category filter</Label>
                  <div className="flex flex-wrap gap-2">
                    {AVAILABLE_CATEGORIES.map((category) => {
                      const active =
                        settings.categories?.includes(category.value) ?? false;
                      return (
                        <button
                          key={category.value}
                          type="button"
                          onClick={() =>
                            setSettings((current) => {
                              const currentCategories = current.categories ?? [];
                              return {
                                ...current,
                                categories: active
                                  ? currentCategories.filter(
                                      (value) => value !== category.value,
                                    )
                                  : [...currentCategories, category.value],
                              };
                            })
                          }
                          className={`rounded-full border px-3 py-2 text-sm transition ${
                            active
                              ? "border-amber-300/20 bg-amber-300/12 text-amber-200"
                              : "border-white/10 bg-white/5 text-white/68"
                          }`}
                        >
                          {category.value}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="rounded-[24px] border border-dashed border-white/10 bg-white/5 p-4 text-sm leading-6 text-muted-foreground">
                  Streaming is the default path. If it fails, the client falls back to the standard non-streaming ask route for the same workspace.
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left">
          <div className="space-y-2">
            <h2 className="font-serif text-3xl font-semibold">Workspaces</h2>
            <p className="text-sm text-muted-foreground">
              Jump between persistent general chats and project-specific threads.
            </p>
          </div>
          <div className="overflow-y-auto pr-1">{renderSidebar()}</div>
        </SheetContent>
      </Sheet>

      <Dialog open={projectDialogOpen} onOpenChange={setProjectDialogOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Create Project</DialogTitle>
            <DialogDescription>
              Projects keep a separate source list and a separate persisted chat thread.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="project-name">Name</Label>
              <Input
                id="project-name"
                value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)}
                placeholder="Benchmarking multimodal retrieval"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="project-description">Description</Label>
              <Textarea
                id="project-description"
                value={newProjectDescription}
                onChange={(event) => setNewProjectDescription(event.target.value)}
                placeholder="Optional context for this research track"
                className="min-h-[130px]"
              />
            </div>

            <Button
              className="w-full"
              disabled={
                createProjectMutation.isPending || newProjectName.trim().length === 0
              }
              onClick={() => createProjectMutation.mutate()}
            >
              <FolderPlus className="h-4 w-4" />
              {createProjectMutation.isPending ? "Creating..." : "Create project"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function SidebarSessionButton({
  active,
  onSelect,
  session,
}: {
  active: boolean;
  onSelect: (sessionId: string) => void;
  session: ChatSessionSummary;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(session.id)}
      className={cn(
        "w-full rounded-[24px] border px-4 py-3 text-left transition",
        active
          ? "border-amber-300/25 bg-amber-300/12 text-white"
          : "border-white/10 bg-white/5 text-white/75 hover:bg-white/8",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="font-medium">{session.title ?? "Untitled chat"}</p>
          <p className="text-xs text-white/55">
            {session.message_count} messages
          </p>
        </div>
        <span className="text-xs text-white/45">
          {formatDate(session.updated_at)}
        </span>
      </div>
    </button>
  );
}

function SidebarProjectButton({
  active,
  onSelect,
  project,
}: {
  active: boolean;
  onSelect: (projectId: string) => void;
  project: ProjectSummary;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(project.id)}
      className={cn(
        "w-full rounded-[24px] border px-4 py-3 text-left transition",
        active
          ? "border-amber-300/25 bg-amber-300/12 text-white"
          : "border-white/10 bg-white/5 text-white/75 hover:bg-white/8",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="font-medium">{project.name}</p>
          <p className="text-xs text-white/55">
            {project.source_count} sources
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-white/45">
          <FolderKanban className="h-3.5 w-3.5" />
          {formatDate(project.updated_at)}
        </div>
      </div>
    </button>
  );
}

function updateAssistantMessage(
  message: ChatMessage,
  event: StreamChunkEvent,
): ChatMessage {
  return {
    ...message,
    content:
      event.answer ??
      (event.chunk ? `${message.content}${event.chunk}` : message.content),
    sources: event.sources ?? message.sources,
    chunksUsed: event.chunks_used ?? message.chunksUsed,
    searchMode: event.search_mode ?? message.searchMode,
    status: event.error ? "error" : event.done ? "complete" : "streaming",
  };
}

async function invalidateWorkspaceQueries(
  queryClient: QueryClient,
  workspace: WorkspaceSelection,
) {
  if (workspace.type === "project") {
    await queryClient.invalidateQueries({
      queryKey: ["projects", "chat", workspace.id],
    });
    await queryClient.invalidateQueries({
      queryKey: ["projects", "detail", workspace.id],
    });
    await queryClient.invalidateQueries({ queryKey: ["projects", "list"] });
    return;
  }

  if (!workspace.id) {
    return;
  }

  await queryClient.invalidateQueries({
    queryKey: ["chat", "session", workspace.id],
  });
  await queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
}
