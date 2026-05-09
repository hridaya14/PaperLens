"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, SearchSlash } from "lucide-react";
import { useState } from "react";
import { APP_TAGLINE, APP_TITLE, NAV_ITEMS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-background/80 backdrop-blur-xl">
      <div className="container flex h-20 items-center justify-between gap-6">
        <Link href="/" className="flex min-w-0 items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-400 text-xs font-semibold uppercase tracking-[0.24em] text-graphite-900">
            PL
          </div>
          <div className="min-w-0">
            <p className="font-serif text-2xl font-semibold tracking-tight">{APP_TITLE}</p>
            <p className="text-sm text-muted-foreground">{APP_TAGLINE}</p>
          </div>
        </Link>

        <nav className="hidden items-center gap-2 md:flex">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  active ? "bg-white/10 text-white" : "text-muted-foreground hover:bg-white/8 hover:text-white"
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Button asChild size="sm" variant="secondary">
            <Link href="/papers">Open Library</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/chat">Launch Assistant</Link>
          </Button>
        </div>

        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild className="md:hidden">
            <Button variant="ghost" size="icon" aria-label="Open navigation">
              <Menu className="h-5 w-5" />
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-sm rounded-[28px]">
            <DialogTitle className="font-serif text-2xl">Navigate PaperLens</DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">
              Jump between the overview, paper workspace, and the streaming research assistant.
            </DialogDescription>
            <div className="mt-4 grid gap-3">
              {NAV_ITEMS.map((item) => {
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "rounded-2xl border px-4 py-3 text-base font-medium",
                      active
                        ? "border-white/10 bg-white/10 text-white"
                        : "border-white/10 bg-white/5 text-white/72"
                    )}
                    onClick={() => setOpen(false)}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
            <div className="mt-4 rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
              <div className="mb-2 flex items-center gap-2 font-medium text-white">
                <SearchSlash className="h-4 w-4" />
                API-backed workspace
              </div>
              The Next.js frontend talks to FastAPI through same-origin proxy routes, so no browser CORS setup is needed.
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </header>
  );
}
