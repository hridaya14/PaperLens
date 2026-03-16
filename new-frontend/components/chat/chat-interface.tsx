"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Cpu, PauseCircle, SendHorizonal, Sparkles, Trash2, User2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { AVAILABLE_CATEGORIES, CHAT_MODELS } from "@/lib/constants";
import { postChat, postChatStream } from "@/lib/api/client";
import type { ChatRequest, StreamChunkEvent } from "@/lib/schemas";
import { readChatStream } from "@/lib/stream";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  chunksUsed?: number;
  searchMode?: string;
  status?: "streaming" | "complete" | "error";
};

export function ChatInterface() {
  const [settings, setSettings] = useState<Omit<ChatRequest, "query">>({
    top_k: 3,
    use_hybrid: true,
    model: CHAT_MODELS[0],
    categories: null
  });
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const scrollViewportRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const viewport = scrollViewportRef.current;
    if (!viewport) {
      return;
    }
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSubmit() {
    const trimmed = query.trim();
    if (!trimmed || isStreaming) {
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed
    };
    const assistantMessageId = crypto.randomUUID();
    const payload: ChatRequest = {
      query: trimmed,
      top_k: settings.top_k,
      use_hybrid: settings.use_hybrid,
      model: settings.model,
      categories: settings.categories
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
        status: "streaming"
      }
    ]);
    setQuery("");
    setIsStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await postChatStream(payload, controller.signal);

      await readChatStream(response, {
        onChunk: (event) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId ? updateAssistantMessage(message, event) : message
            )
          );
        },
        onComplete: (answer) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: answer,
                    status: "complete"
                  }
                : message
            )
          );
        }
      });
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMessageId
              ? {
                  ...message,
                  content: `${message.content}\n\nGeneration stopped.`,
                  status: "error"
                }
              : message
          )
        );
      } else {
        try {
          const fallback = await postChat(payload);
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: fallback.answer,
                    sources: fallback.sources,
                    chunksUsed: fallback.chunks_used,
                    searchMode: fallback.search_mode,
                    status: "complete"
                  }
                : message
            )
          );
        } catch (fallbackError) {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content:
                      fallbackError instanceof Error ? fallbackError.message : "Unable to generate an answer at this time.",
                    status: "error"
                  }
                : message
            )
          );
        }
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }

  function stopStreaming() {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setIsStreaming(false);
  }

  return (
    <section className="container py-10">
      <div className="mb-8 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="max-w-3xl">
          <div className="eyebrow mb-4">Streaming assistant</div>
          <h1 className="font-serif text-5xl font-semibold tracking-tight">Ask grounded questions across your paper collection.</h1>
          <p className="mt-4 text-lg leading-8 text-muted-foreground">
            The interface preserves the prototype RAG controls, but streams answers live and keeps source metadata visible as the reply forms.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Badge>{settings.use_hybrid ? "Hybrid retrieval" : "BM25 mode"}</Badge>
          <Badge variant="muted">{settings.top_k} chunks</Badge>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="h-fit xl:sticky xl:top-28">
          <CardHeader>
            <CardTitle>RAG Settings</CardTitle>
            <CardDescription>These map directly to the backend request contract used by the existing Streamlit assistant.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="top-k">Top K Chunks</Label>
                <span className="text-sm text-muted-foreground">{settings.top_k}</span>
              </div>
              <Slider
                id="top-k"
                min={1}
                max={10}
                step={1}
                value={[settings.top_k]}
                onValueChange={([value]) => setSettings((current) => ({ ...current, top_k: value }))}
              />
            </div>

            <div className="flex items-center justify-between rounded-[24px] border border-white/10 bg-white/5 p-4">
              <div>
                <p className="text-sm font-medium">Use hybrid search</p>
                <p className="text-xs leading-5 text-muted-foreground">Combine BM25 and dense embeddings when available.</p>
              </div>
              <Switch
                checked={settings.use_hybrid}
                onCheckedChange={(checked) => setSettings((current) => ({ ...current, use_hybrid: checked }))}
              />
            </div>

            <label className="space-y-2">
              <span className="block text-sm font-medium">Model</span>
              <select
                value={settings.model}
                onChange={(event) => setSettings((current) => ({ ...current, model: event.target.value }))}
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
                  const active = settings.categories?.includes(category.value) ?? false;
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
                              ? currentCategories.filter((value) => value !== category.value)
                              : [...currentCategories, category.value]
                          };
                        })
                      }
                      className={`rounded-full border px-3 py-2 text-sm transition ${
                        active ? "border-amber-300/20 bg-amber-300/12 text-amber-200" : "border-white/10 bg-white/5 text-white/68"
                      }`}
                    >
                      {category.value}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="rounded-[24px] border border-dashed border-white/10 bg-white/5 p-4 text-sm leading-6 text-muted-foreground">
              Streaming is the default path. If it fails, the client falls back to the standard non-streaming `/ask` proxy automatically.
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <div ref={scrollViewportRef} className="h-[560px] space-y-4 overflow-y-auto p-6">
                  {messages.length === 0 ? (
                    <div className="flex min-h-[480px] flex-col items-center justify-center gap-4 text-center">
                      <Sparkles className="h-10 w-10 text-paper-500" />
                      <p className="font-serif text-3xl font-semibold">Start a research conversation.</p>
                      <p className="max-w-xl text-sm leading-6 text-muted-foreground">
                        Ask about one paper, a cluster of ideas, or trends across the indexed corpus. Responses are grounded in retrieved chunks and show source PDFs.
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
                          className={`flex gap-4 ${message.role === "assistant" ? "" : "justify-end"}`}
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
                                <ReactMarkdown>{message.content || "Thinking..."}</ReactMarkdown>
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
                                  {message.chunksUsed ? <Badge variant="muted">{message.chunksUsed} chunks</Badge> : null}
                                  {message.status === "streaming" ? <Badge variant="muted">Streaming</Badge> : null}
                                </div>
                                {message.sources?.length ? (
                                  <Accordion type="single" collapsible className="rounded-[20px] border border-white/10 bg-black/15 px-4">
                                    <AccordionItem value="sources" className="border-none">
                                      <AccordionTrigger>Sources</AccordionTrigger>
                                      <AccordionContent>
                                        <ul className="space-y-2 text-sm">
                                          {message.sources.map((source) => (
                                            <li key={source}>
                                              <a href={source} target="_blank" rel="noreferrer" className="text-amber-200 underline underline-offset-4">
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
              <Label htmlFor="chat-query">Ask a question about your papers</Label>
              <Textarea
                id="chat-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="What problem does this paper solve? How do recent multimodal approaches differ from earlier work?"
                onKeyDown={(event) => {
                  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                    event.preventDefault();
                    void handleSubmit();
                  }
                }}
                className="min-h-[140px]"
              />
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Press Cmd/Ctrl + Enter to send</p>
                <div className="flex flex-wrap gap-3">
                  <Button variant="outline" onClick={() => setMessages([])}>
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
      </div>
    </section>
  );
}

function updateAssistantMessage(message: ChatMessage, event: StreamChunkEvent): ChatMessage {
  return {
    ...message,
    content: event.answer ?? (event.chunk ? `${message.content}${event.chunk}` : message.content),
    sources: event.sources ?? message.sources,
    chunksUsed: event.chunks_used ?? message.chunksUsed,
    searchMode: event.search_mode ?? message.searchMode,
    status: event.error ? "error" : event.done ? "complete" : "streaming"
  };
}
