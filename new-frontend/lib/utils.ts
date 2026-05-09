import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value?: string | Date | null) {
  if (!value) {
    return "Unknown date";
  }

  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) {
    return "Unknown date";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  }).format(date);
}

export function truncateText(text: string, length = 240) {
  if (text.length <= length) {
    return text;
  }

  return `${text.slice(0, length).trim()}...`;
}

export function ensureArray<T>(value: T | T[] | null | undefined) {
  if (value === undefined || value === null) {
    return [] as T[];
  }

  return Array.isArray(value) ? value : [value];
}

export function buildQueryString(params: Record<string, string | number | boolean | undefined | null | string[]>) {
  const searchParams = new URLSearchParams();

  for (const [key, rawValue] of Object.entries(params)) {
    if (rawValue === undefined || rawValue === null || rawValue === "") {
      continue;
    }

    if (Array.isArray(rawValue)) {
      for (const item of rawValue) {
        searchParams.append(key, item);
      }
      continue;
    }

    searchParams.set(key, String(rawValue));
  }

  return searchParams.toString();
}
