"use client";

import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Layers,
  Pencil,
  Plus,
  RefreshCw,
  Shield,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import {
  activateScopeProfile,
  createScopeProfile,
  deleteScopeProfile,
  getScopeProfileDecisionStats,
  listScopeProfiles,
  recomputeScopeVector,
  updateScopeProfile,
} from "@/lib/api/client";
import type { ScopeProfile } from "@/lib/schemas";
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
import { Textarea } from "@/components/ui/textarea";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ProfileFormState = {
  name: string;
  description: string;
  required_terms: string;
  excluded_terms: string;
  lexical_match_mode: "any" | "all";
  composite_ingest: string;
  relevance_weight: string;
  venue_weight: string;
  citation_weight: string;
  embedding_high: string;
  embedding_low: string;
};

const emptyForm: ProfileFormState = {
  name: "",
  description: "",
  required_terms: "",
  excluded_terms: "",
  lexical_match_mode: "any",
  composite_ingest: "0.72",
  relevance_weight: "0.70",
  venue_weight: "0.15",
  citation_weight: "0.15",
  embedding_high: "0.82",
  embedding_low: "0.60",
};

function profileToForm(p: ScopeProfile): ProfileFormState {
  return {
    name: p.name,
    description: p.description ?? "",
    required_terms: (p.required_terms ?? []).join(", "),
    excluded_terms: (p.excluded_terms ?? []).join(", "),
    lexical_match_mode: p.lexical_match_mode ?? "any",
    composite_ingest: String(p.thresholds?.composite_ingest ?? 0.72),
    relevance_weight: String(p.scoring_weights?.relevance ?? 0.70),
    venue_weight: String(p.scoring_weights?.venue ?? 0.15),
    citation_weight: String(p.scoring_weights?.citation ?? 0.15),
    embedding_high: String(p.thresholds?.embedding_high ?? 0.82),
    embedding_low: String(p.thresholds?.embedding_low ?? 0.60),
  };
}

function splitTerms(raw: string): string[] {
  return raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({ label, value, sub }: { label: string; value: string | number | null | undefined; sub?: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-white">
        {value ?? "—"}
      </p>
      {sub ? <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p> : null}
    </div>
  );
}

function DecisionStatsPanel({ profileId }: { profileId: string }) {
  const statsQuery = useQuery({
    queryKey: ["scope-profile-stats", profileId],
    queryFn: () => getScopeProfileDecisionStats(profileId),
  });

  if (statsQuery.isLoading) {
    return (
      <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
        Loading decision stats…
      </div>
    );
  }

  if (statsQuery.isError) {
    return (
      <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-500/10 p-4 text-sm text-rose-200">
        Could not load decision stats.
      </div>
    );
  }

  const s = statsQuery.data;
  const rate = s?.acceptance_rate != null ? `${(s.acceptance_rate * 100).toFixed(1)}%` : null;

  return (
    <div className="mt-4 space-y-3">
      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        <BarChart3 className="h-3.5 w-3.5" />
        Decision stats
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total decisions" value={s?.total} />
        <StatCard label="Accepted" value={s?.ingested} />
        <StatCard label="Rejected" value={s?.rejected} />
        <StatCard label="Acceptance rate" value={rate} />
      </div>
      {s?.avg_composite_score != null && (
        <div className="grid gap-3 sm:grid-cols-2">
          <StatCard
            label="Avg composite score"
            value={s.avg_composite_score.toFixed(3)}
          />
          {s.avg_semantic_score != null && (
            <StatCard
              label="Avg semantic score"
              value={s.avg_semantic_score.toFixed(3)}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Profile form (create / edit)
// ---------------------------------------------------------------------------

function ProfileForm({
  initial,
  onSubmit,
  onCancel,
  submitting,
}: {
  initial: ProfileFormState;
  onSubmit: (form: ProfileFormState) => void;
  onCancel: () => void;
  submitting: boolean;
}) {
  const [form, setForm] = useState<ProfileFormState>(initial);

  function field(key: keyof ProfileFormState) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((prev) => ({ ...prev, [key]: e.target.value }));
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="pf-name">Profile name *</Label>
          <Input
            id="pf-name"
            placeholder="e.g. NLP core"
            value={form.name}
            onChange={field("name")}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="pf-mode">Lexical match mode</Label>
          <select
            id="pf-mode"
            value={form.lexical_match_mode}
            onChange={field("lexical_match_mode")}
            className="field-surface h-12 w-full appearance-none rounded-2xl px-4 text-sm outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="any">any — at least one required term</option>
            <option value="all">all — every required term must match</option>
          </select>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="pf-desc">Description</Label>
        <Textarea
          id="pf-desc"
          placeholder="Describe the research scope this profile targets…"
          value={form.description}
          onChange={field("description")}
          rows={3}
        />
        <p className="text-xs text-muted-foreground">
          Used to compute the semantic scope vector. Be specific about topics and methods.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="pf-required">Required terms</Label>
          <Input
            id="pf-required"
            placeholder="transformer, attention (comma-separated)"
            value={form.required_terms}
            onChange={field("required_terms")}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="pf-excluded">Excluded terms</Label>
          <Input
            id="pf-excluded"
            placeholder="survey, review (comma-separated)"
            value={form.excluded_terms}
            onChange={field("excluded_terms")}
          />
        </div>
      </div>

      <Separator />

      <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Scoring weights
      </p>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor="pf-rel-w">Relevance weight</Label>
          <Input id="pf-rel-w" type="number" step="0.05" min="0" max="1"
            value={form.relevance_weight} onChange={field("relevance_weight")} />
          <p className="text-xs text-muted-foreground">Must sum to 1.0 with venue + citation.</p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="pf-venue-w">Venue weight</Label>
          <Input id="pf-venue-w" type="number" step="0.05" min="0" max="1"
            value={form.venue_weight} onChange={field("venue_weight")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="pf-cit-w">Citation weight</Label>
          <Input id="pf-cit-w" type="number" step="0.05" min="0" max="1"
            value={form.citation_weight} onChange={field("citation_weight")} />
        </div>
      </div>

      <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Filtering thresholds
      </p>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor="pf-emb-high">Embedding high (fast-track ingest)</Label>
          <Input id="pf-emb-high" type="number" step="0.01" min="0" max="1"
            value={form.embedding_high} onChange={field("embedding_high")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="pf-emb-low">Embedding low (fast-track reject)</Label>
          <Input id="pf-emb-low" type="number" step="0.01" min="0" max="1"
            value={form.embedding_low} onChange={field("embedding_low")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="pf-composite">Composite ingest threshold</Label>
          <Input id="pf-composite" type="number" step="0.01" min="0" max="1"
            value={form.composite_ingest} onChange={field("composite_ingest")} />
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Button onClick={() => onSubmit(form)} disabled={submitting || !form.name.trim()}>
          <Sparkles className="h-4 w-4" />
          {submitting ? "Saving…" : "Save profile"}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single profile card
// ---------------------------------------------------------------------------

function ProfileCard({
  profile,
  isActive,
  onActivate,
  onRecompute,
  onEdit,
  onDelete,
}: {
  profile: ScopeProfile;
  isActive: boolean;
  onActivate: () => void;
  onRecompute: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  return (
    <div
      className={`rounded-[24px] border transition-colors ${
        isActive
          ? "border-amber-400/30 bg-amber-400/6"
          : "border-white/10 bg-white/4"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-4 p-5">
        <div className="flex min-w-0 flex-1 items-start gap-4">
          <div
            className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${
              isActive ? "bg-amber-400 text-graphite-900" : "bg-white/8 text-white/60"
            }`}
          >
            {isActive ? <Shield className="h-4 w-4" /> : <Layers className="h-4 w-4" />}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-serif text-lg font-semibold text-white">{profile.name}</p>
              {isActive && (
                <Badge variant="default" className="text-xs">Active</Badge>
              )}
              {profile.has_scope_vector && (
                <Badge variant="muted" className="text-xs">Vector ready</Badge>
              )}
            </div>
            {profile.description && (
              <p className="mt-1 text-sm leading-6 text-muted-foreground line-clamp-2">
                {profile.description}
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
              {profile.required_terms?.length > 0 && (
                <span>Required: {profile.required_terms.slice(0, 4).join(", ")}{profile.required_terms.length > 4 ? "…" : ""}</span>
              )}
              {profile.excluded_terms?.length > 0 && (
                <span>Excluded: {profile.excluded_terms.slice(0, 3).join(", ")}{profile.excluded_terms.length > 3 ? "…" : ""}</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!isActive && (
            <Button size="sm" variant="outline" onClick={onActivate}>
              <Zap className="h-3.5 w-3.5" />
              Activate
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onRecompute}>
            <Cpu className="h-3.5 w-3.5" />
            Recompute vector
          </Button>
          <Button size="sm" variant="outline" onClick={onEdit}>
            <Pencil className="h-3.5 w-3.5" />
            Edit
          </Button>
          <Button
            size="sm"
            variant="outline"
            className={deleteConfirm ? "border-rose-400/40 text-rose-200" : ""}
            onClick={() => {
              if (!deleteConfirm) {
                setDeleteConfirm(true);
                setTimeout(() => setDeleteConfirm(false), 3000);
              } else {
                onDelete();
              }
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deleteConfirm ? "Confirm delete" : "Delete"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setExpanded((v) => !v)}>
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-white/8 px-5 pb-5 pt-4">
          <div className="grid gap-3 sm:grid-cols-3 text-sm">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
              <p className="text-xs text-muted-foreground mb-1">Lexical mode</p>
              <p className="font-medium text-white capitalize">{profile.lexical_match_mode}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
              <p className="text-xs text-muted-foreground mb-1">Composite ingest threshold</p>
              <p className="font-medium text-white">{profile.thresholds?.composite_ingest ?? 0.72}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
              <p className="text-xs text-muted-foreground mb-1">Weights (rel / venue / cit)</p>
              <p className="font-medium text-white">
                {profile.scoring_weights?.relevance ?? 0.7} / {profile.scoring_weights?.venue ?? 0.15} / {profile.scoring_weights?.citation ?? 0.15}
              </p>
            </div>
          </div>

          <DecisionStatsPanel profileId={profile.id} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main workspace
// ---------------------------------------------------------------------------

export function ScopeProfileWorkspace() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"list" | "create" | "edit">("list");
  const [editingProfile, setEditingProfile] = useState<ScopeProfile | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  function showFeedback(type: "success" | "error", message: string) {
    setFeedback({ type, message });
    setTimeout(() => setFeedback(null), 5000);
  }

  const profilesQuery = useQuery({
    queryKey: ["scope-profiles"],
    queryFn: listScopeProfiles,
  });

  const createMutation = useMutation({
    mutationFn: createScopeProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scope-profiles"] });
      setMode("list");
      showFeedback("success", "Profile created.");
    },
    onError: (err: Error) => showFeedback("error", err.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof updateScopeProfile>[1] }) =>
      updateScopeProfile(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scope-profiles"] });
      setMode("list");
      setEditingProfile(null);
      showFeedback("success", "Profile updated.");
    },
    onError: (err: Error) => showFeedback("error", err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteScopeProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scope-profiles"] });
      showFeedback("success", "Profile deleted.");
    },
    onError: (err: Error) => showFeedback("error", err.message),
  });

  const activateMutation = useMutation({
    mutationFn: activateScopeProfile,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["scope-profiles"] });
      showFeedback("success", data.message);
    },
    onError: (err: Error) => showFeedback("error", err.message),
  });

  const recomputeMutation = useMutation({
    mutationFn: recomputeScopeVector,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["scope-profiles"] });
      showFeedback("success", data.message);
    },
    onError: (err: Error) => showFeedback("error", err.message),
  });

  const handleFormSubmit = useCallback(
    (form: ProfileFormState) => {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        required_terms: splitTerms(form.required_terms),
        excluded_terms: splitTerms(form.excluded_terms),
        lexical_match_mode: form.lexical_match_mode,
        thresholds: {
          composite_ingest: parseFloat(form.composite_ingest) || 0.72,
          embedding_high: parseFloat(form.embedding_high) || 0.82,
          embedding_low: parseFloat(form.embedding_low) || 0.60,
        },
        scoring_weights: {
          relevance: parseFloat(form.relevance_weight) || 0.70,
          venue: parseFloat(form.venue_weight) || 0.15,
          citation: parseFloat(form.citation_weight) || 0.15,
        },
      };

      if (mode === "create") {
        createMutation.mutate(payload);
      } else if (editingProfile) {
        updateMutation.mutate({ id: editingProfile.id, payload });
      }
    },
    [mode, editingProfile, createMutation, updateMutation],
  );

  const profiles = profilesQuery.data?.profiles ?? [];
  const activeId = profilesQuery.data?.active_profile_id;

  return (
    <section className="container py-10">
      <div className="mb-8 flex flex-col gap-4">
        <div className="eyebrow">Scope Profiles</div>
        <h1 className="font-serif text-5xl font-semibold tracking-tight text-foreground">
          Research filter preferences.
        </h1>
        <p className="max-w-3xl text-lg leading-8 text-muted-foreground">
          Scope profiles control how PaperLens filters and ranks incoming papers. Define required
          terms, excluded topics, scoring weights, and thresholds. Activate a profile to apply it
          to future pipeline runs.
        </p>
      </div>

      {feedback && (
        <div
          className={`mb-6 flex items-center gap-3 rounded-2xl border p-4 text-sm ${
            feedback.type === "success"
              ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-200"
              : "border-rose-400/20 bg-rose-500/10 text-rose-200"
          }`}
        >
          {feedback.type === "success" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" />
          ) : (
            <AlertTriangle className="h-4 w-4 shrink-0" />
          )}
          {feedback.message}
        </div>
      )}

      {mode !== "list" ? (
        <Card>
          <CardHeader>
            <CardTitle>{mode === "create" ? "Create a new profile" : `Edit "${editingProfile?.name}"`}</CardTitle>
            <CardDescription>
              {mode === "create"
                ? "Define the scope this profile will apply when filtering papers."
                : "Update the profile settings. Changing content fields will clear the scope vector — recompute it after saving."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ProfileForm
              initial={mode === "edit" && editingProfile ? profileToForm(editingProfile) : emptyForm}
              onSubmit={handleFormSubmit}
              onCancel={() => {
                setMode("list");
                setEditingProfile(null);
              }}
              submitting={createMutation.isPending || updateMutation.isPending}
            />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              {profilesQuery.isLoading
                ? "Loading…"
                : `${profiles.length} profile${profiles.length !== 1 ? "s" : ""}${activeId ? " · 1 active" : ""}`}
            </p>
            <div className="flex gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => profilesQuery.refetch()}
                disabled={profilesQuery.isLoading}
              >
                <RefreshCw className={`h-4 w-4 ${profilesQuery.isFetching ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              <Button size="sm" onClick={() => setMode("create")}>
                <Plus className="h-4 w-4" />
                New profile
              </Button>
            </div>
          </div>

          {profilesQuery.isError ? (
            <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 p-5 text-sm text-rose-200">
              <div className="mb-2 flex items-center gap-2 font-semibold">
                <AlertTriangle className="h-4 w-4" />
                Failed to load profiles
              </div>
              {(profilesQuery.error as Error)?.message}
            </div>
          ) : profiles.length === 0 && !profilesQuery.isLoading ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-10 text-center">
              <Layers className="mx-auto mb-4 h-10 w-10 text-white/20" />
              <p className="font-medium text-white">No scope profiles yet</p>
              <p className="mt-2 text-sm text-muted-foreground">
                Create your first profile to start controlling how papers are filtered.
              </p>
              <Button className="mt-5" onClick={() => setMode("create")}>
                <Plus className="h-4 w-4" />
                Create first profile
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {profiles.map((profile) => (
                <ProfileCard
                  key={profile.id}
                  profile={profile}
                  isActive={profile.id === activeId}
                  onActivate={() => activateMutation.mutate(profile.id)}
                  onRecompute={() => recomputeMutation.mutate(profile.id)}
                  onEdit={() => {
                    setEditingProfile(profile);
                    setMode("edit");
                  }}
                  onDelete={() => deleteMutation.mutate(profile.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
