"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Layers3, RefreshCw, Shuffle, Undo2 } from "lucide-react";
import type { Paper } from "@/lib/schemas";
import { getFlashcards } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type FlashcardDialogProps = {
  paper: Paper | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function FlashcardDialog({
  paper,
  open,
  onOpenChange,
}: FlashcardDialogProps) {
  const arxivId = paper?.arxiv_id ?? null;
  const flashcardQuery = useQuery({
    queryKey: ["flashcards", arxivId],
    queryFn: () => {
      if (!arxivId) {
        return Promise.reject(new Error("Missing arXiv ID"));
      }
      return getFlashcards(arxivId, { numCards: 15 });
    },
    enabled: open && Boolean(arxivId),
  });

  const [cards, setCards] = useState<ReturnType<typeof getCardList>>([]);
  const [index, setIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [studied, setStudied] = useState<string[]>([]);
  const [topicFilter, setTopicFilter] = useState("All");

  useEffect(() => {
    if (flashcardQuery.data) {
      const nextCards = getCardList(flashcardQuery.data);
      setCards(nextCards);
      setIndex(0);
      setShowAnswer(false);
      setStudied([]);
      setTopicFilter("All");
    }
  }, [flashcardQuery.data]);

  const availableTopics = [
    "All",
    ...Array.from(
      new Set(
        cards
          .map((card) => card.topic)
          .filter((topic): topic is string => Boolean(topic)),
      ),
    ),
  ];
  const visibleCards =
    topicFilter === "All"
      ? cards
      : cards.filter((card) => card.topic === topicFilter);
  const currentCard = visibleCards[index] ?? null;
  const progress = visibleCards.length
    ? Math.min(index + 1, visibleCards.length)
    : 0;
  const studiedCount = studied.filter((cardId) =>
    visibleCards.some((card) => card.id === cardId),
  ).length;

  useEffect(() => {
    setIndex(0);
    setShowAnswer(false);
  }, [topicFilter]);

  function markStudied(cardId: string) {
    setStudied((current) =>
      current.includes(cardId) ? current : [...current, cardId],
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="panel-dark max-w-5xl overflow-hidden border-white/10 bg-[linear-gradient(180deg,#101817,#182321)] p-0 text-white">
        <DialogHeader className="border-b border-white/10 px-8 py-6">
          <div className="mb-3 flex items-center gap-3">
            <div className="eyebrow border-white/10 bg-white/5 text-paper-100">
              Study mode
            </div>
            {flashcardQuery.data?.meta?.is_cached ? (
              <Badge variant="dark">Cached set</Badge>
            ) : null}
          </div>
          <DialogTitle className="text-white">
            {paper?.title ?? "Flashcards"}
          </DialogTitle>
          <DialogDescription className="text-white/68">
            Notebook-style flashcards generated from indexed sections. Flip
            cards, shuffle the deck, and focus by topic.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 p-8 lg:grid-cols-[1.15fr_0.6fr]">
          <div className="space-y-5">
            {!paper?.arxiv_id ? (
              <div className="flex min-h-[420px] items-center justify-center rounded-[30px] border border-white/10 bg-white/5 px-6 text-center text-sm text-white/70">
                Flashcards are only available for arXiv-sourced papers right
                now. Uploads can still be read in the PDF viewer.
              </div>
            ) : flashcardQuery.isLoading ? (
              <div className="flex min-h-[420px] items-center justify-center rounded-[30px] border border-white/10 bg-white/5 text-sm text-white/70">
                Generating flashcards. First load can take a little while.
              </div>
            ) : flashcardQuery.isError ? (
              <div className="flex min-h-[420px] items-center justify-center rounded-[30px] border border-rose-400/20 bg-rose-500/10 px-6 text-center text-sm text-rose-100">
                {flashcardQuery.error instanceof Error
                  ? flashcardQuery.error.message
                  : "Unable to load flashcards."}
              </div>
            ) : currentCard ? (
              <>
                <div className="flex items-center justify-between gap-4 text-sm text-white/68">
                  <p>
                    Card {progress} of {visibleCards.length}
                  </p>
                  <p>{studiedCount} reviewed</p>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-paper-300 via-paper-400 to-orange-400"
                    style={{
                      width: `${visibleCards.length ? (progress / visibleCards.length) * 100 : 0}%`,
                    }}
                  />
                </div>
                <AnimatePresence mode="wait">
                  <motion.div
                    key={`${currentCard.id}-${showAnswer ? "answer" : "question"}`}
                    initial={{ opacity: 0, y: 14, rotateX: -8 }}
                    animate={{ opacity: 1, y: 0, rotateX: 0 }}
                    exit={{ opacity: 0, y: -10, rotateX: 8 }}
                    transition={{ duration: 0.24 }}
                    className={`min-h-[360px] rounded-[32px] border p-8 shadow-2xl ${
                      showAnswer
                        ? "border-rose-300/20 bg-[linear-gradient(160deg,rgba(255,146,146,0.16),rgba(236,72,153,0.08))]"
                        : "border-sky-300/20 bg-[linear-gradient(160deg,rgba(103,211,255,0.18),rgba(30,64,175,0.08))]"
                    }`}
                  >
                    <div className="mb-8 flex items-center justify-between gap-4">
                      <Badge variant="dark">
                        {showAnswer ? "Answer" : "Question"}
                      </Badge>
                      <div className="flex gap-2">
                        {currentCard.topic ? (
                          <Badge variant="dark">{currentCard.topic}</Badge>
                        ) : null}
                        {currentCard.difficulty ? (
                          <Badge variant="dark">{currentCard.difficulty}</Badge>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex min-h-[240px] items-center justify-center">
                      <p className="max-w-2xl text-center font-serif text-3xl leading-[1.35] text-white">
                        {showAnswer ? currentCard.back : currentCard.front}
                      </p>
                    </div>
                  </motion.div>
                </AnimatePresence>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Button
                    variant="outline"
                    className="border-white/15 bg-white/5 text-white hover:bg-white/10"
                    disabled={index === 0}
                    onClick={() => {
                      setIndex((current) => Math.max(0, current - 1));
                      setShowAnswer(false);
                    }}
                  >
                    Previous
                  </Button>
                  <Button
                    onClick={() => {
                      setShowAnswer((current) => !current);
                      if (!showAnswer) {
                        markStudied(currentCard.id);
                      }
                    }}
                  >
                    {showAnswer ? "Show Question" : "Show Answer"}
                  </Button>
                  <Button
                    variant="outline"
                    className="border-white/15 bg-white/5 text-white hover:bg-white/10"
                    disabled={index >= visibleCards.length - 1}
                    onClick={() => {
                      setIndex((current) =>
                        Math.min(visibleCards.length - 1, current + 1),
                      );
                      setShowAnswer(false);
                    }}
                  >
                    Next
                  </Button>
                </div>
              </>
            ) : (
              <div className="flex min-h-[420px] items-center justify-center rounded-[30px] border border-white/10 bg-white/5 text-sm text-white/70">
                No flashcards available for the current filter.
              </div>
            )}
          </div>

          <div className="space-y-4 rounded-[30px] border border-white/10 bg-white/5 p-6">
            <div className="flex items-center gap-2 text-white">
              <Layers3 className="h-4 w-4" />
              Deck controls
            </div>
            <div className="grid gap-3">
              <label className="space-y-2 text-sm text-white/68">
                <span className="block">Topic focus</span>
                <select
                  value={topicFilter}
                  onChange={(event) => setTopicFilter(event.target.value)}
                  className="field-surface h-12 w-full appearance-none rounded-2xl px-4 text-sm outline-none"
                >
                  {availableTopics.map((topic) => (
                    <option
                      key={topic}
                      value={topic}
                      className="text-graphite-900"
                    >
                      {topic}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                variant="outline"
                className="border-white/15 bg-white/5 text-white hover:bg-white/10"
                onClick={() => {
                  setCards((current) => shuffle(current));
                  setIndex(0);
                  setShowAnswer(false);
                }}
              >
                <Shuffle className="h-4 w-4" />
                Shuffle deck
              </Button>
              <Button
                variant="outline"
                className="border-white/15 bg-white/5 text-white hover:bg-white/10"
                onClick={() => {
                  if (flashcardQuery.data) {
                    setCards(getCardList(flashcardQuery.data));
                  }
                  setIndex(0);
                  setShowAnswer(false);
                  setStudied([]);
                  setTopicFilter("All");
                }}
              >
                <Undo2 className="h-4 w-4" />
                Restart session
              </Button>
              <Button
                variant="outline"
                className="border-white/15 bg-white/5 text-white hover:bg-white/10"
                onClick={() => flashcardQuery.refetch()}
              >
                <RefreshCw className="h-4 w-4" />
                Refresh from API
              </Button>
            </div>
            <div className="rounded-[24px] border border-white/10 bg-black/10 p-4 text-sm text-white/68">
              <p className="mb-2 font-medium text-white">Set metadata</p>
              <p>Total cards: {flashcardQuery.data?.meta?.total_cards ?? 0}</p>
              <p>
                Topics covered:{" "}
                {Array.isArray(flashcardQuery.data?.meta?.topics_covered)
                  ? flashcardQuery.data?.meta?.topics_covered.length
                  : 0}
              </p>
              <p>
                Model:{" "}
                {String(flashcardQuery.data?.meta?.model_used ?? "Unknown")}
              </p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function getCardList(data: Awaited<ReturnType<typeof getFlashcards>>) {
  return data.flashcards.map((card, cardIndex) => ({
    ...card,
    id: String(card.id ?? card.card_index ?? cardIndex),
  }));
}

function shuffle<T>(items: T[]) {
  const next = [...items];
  for (let index = next.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [next[index], next[swapIndex]] = [next[swapIndex], next[index]];
  }
  return next;
}
