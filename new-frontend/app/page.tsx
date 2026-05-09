import Link from "next/link";
import { ArrowRight, Bot, BrainCircuit, FileStack, LayoutDashboard, Network, NotebookTabs } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const capabilities = [
  {
    icon: FileStack,
    title: "Research paper repository",
    description:
      "Browse ingested papers, filter by research category, inspect processing status, and keep frequently referenced work close at hand."
  },
  {
    icon: BrainCircuit,
    title: "Structured knowledge access",
    description:
      "Generate concept maps and study flashcards directly from indexed chunks to move from reading to synthesis faster."
  },
  {
    icon: Bot,
    title: "Retrieval-augmented chat",
    description:
      "Ask questions over the corpus with source-aware responses, configurable retrieval depth, and live streaming output."
  }
];

const architecture = [
  "FastAPI for APIs and RAG orchestration",
  "PostgreSQL for metadata and structured storage",
  "OpenSearch for retrieval and semantic search",
  "Airflow for ingestion and scheduled workflows",
  "Next.js for the upgraded research workstation UI"
];

export default function HomePage() {
  return (
    <div className="pb-16">
      <section className="container pt-14">
        <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="panel-surface overflow-hidden p-8 md:p-10">
            <div className="eyebrow mb-5">Prototype to product-grade frontend</div>
            <h1 className="max-w-4xl font-serif text-5xl font-semibold leading-[1.05] tracking-tight md:text-7xl">
              A research workspace for ingesting, exploring, and reasoning over academic papers.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-muted-foreground">
              PaperLens brings search, reading, concept mapping, flashcards, and corpus-grounded chat into one deliberate environment instead of spreading the workflow across notebooks, PDFs, and external tools.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/papers">
                  Open Papers
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href="/chat">Launch Assistant</Link>
              </Button>
            </div>
          </div>

          <div className="panel-dark grid min-h-[420px] content-between p-8">
            <div>
              <Badge variant="dark">Why this version exists</Badge>
              <p className="mt-5 font-serif text-3xl font-semibold leading-tight text-white">
                Preserve the proven Streamlit workflows, but give them better structure, motion, and room to grow.
              </p>
            </div>
            <div className="grid gap-4">
              <div className="rounded-[26px] border border-white/10 bg-white/5 p-5">
                <div className="mb-3 flex items-center gap-3 text-paper-100">
                  <LayoutDashboard className="h-5 w-5" />
                  Papers workspace
                </div>
                <p className="text-sm leading-6 text-white/68">Responsive filter rail, persistent bookmarks, embedded PDF preview, and richer knowledge views.</p>
              </div>
              <div className="rounded-[26px] border border-white/10 bg-white/5 p-5">
                <div className="mb-3 flex items-center gap-3 text-paper-100">
                  <NotebookTabs className="h-5 w-5" />
                  Study surfaces
                </div>
                <p className="text-sm leading-6 text-white/68">Mind maps use an explorable graph canvas; flashcards become a focused deck instead of a static widget.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="container mt-10 grid gap-6 lg:grid-cols-3">
        {capabilities.map((capability) => (
          <Card key={capability.title}>
            <CardHeader>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/6 text-amber-200">
                <capability.icon className="h-5 w-5" />
              </div>
              <CardTitle>{capability.title}</CardTitle>
              <CardDescription>{capability.description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>

      <section className="container mt-10 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle>What is PaperLens?</CardTitle>
            <CardDescription>
              PaperLens is a research-focused workspace designed to organize, explore, and reason over academic papers efficiently.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 md:grid-cols-2">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-5 text-sm leading-7 text-white/72">
              Instead of juggling PDFs, notes, and retrieval tools, PaperLens keeps ingestion, search, reading, and grounded reasoning in one system.
            </div>
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-5 text-sm leading-7 text-white/72">
              The frontend stays intentionally thin and delegates all search, generation, and storage concerns to backend services through typed proxy routes.
            </div>
          </CardContent>
        </Card>

        <Card className="grid-paper">
          <CardHeader>
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/6 text-amber-200">
              <Network className="h-5 w-5" />
            </div>
            <CardTitle>System architecture</CardTitle>
            <CardDescription>The UI mirrors the current backend topology and stays stateless outside local browser preferences like bookmarks.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {architecture.map((item) => (
              <div key={item} className="rounded-[20px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/72">
                {item}
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
