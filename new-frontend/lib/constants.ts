export const APP_TITLE = "PaperLens";
export const APP_TAGLINE = "Research Workspace";

export const CATEGORY_LABELS: Record<string, string> = {
  "cs.AI": "Artificial Intelligence",
  "cs.CV": "Computer Vision",
  "cs.CL": "Natural Language Processing",
  "cs.LG": "Machine Learning",
  "cs.RO": "Robotics",
  "cs.SY": "Systems",
};

export const AVAILABLE_CATEGORIES = Object.entries(CATEGORY_LABELS).map(
  ([value, label]) => ({
    value,
    label,
  }),
);

export const RESULT_LIMITS = [10, 20, 50] as const;
export const CHAT_MODELS = [
  "meta/llama-3.3-70b-instruct",
  "qwen/qwen3.5-9b",
] as const;

export const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/papers", label: "Papers" },
  { href: "/uploads", label: "Uploads" },
  { href: "/chat", label: "Chat" },
] as const;
