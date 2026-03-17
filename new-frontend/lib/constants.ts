export const APP_TITLE = "PaperLens";
export const APP_TAGLINE = "Search, map, and study your research papers in one place.";

export const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/papers", label: "Papers" },
  { href: "/chat", label: "Assistant" }
] as const;

export const AVAILABLE_CATEGORIES = [
  { value: "cs.AI", label: "Artificial Intelligence" },
  { value: "cs.CL", label: "Natural Language Processing" },
  { value: "cs.CV", label: "Computer Vision" },
  { value: "cs.LG", label: "Machine Learning" },
  { value: "cs.RO", label: "Robotics" },
  { value: "cs.SY", label: "Systems" }
] as const;

export const RESULT_LIMITS = [10, 20, 50] as const;

export const CHAT_MODELS = ["meta/llama-3.3-70b-instruct"] as const;
