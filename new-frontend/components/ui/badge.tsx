import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold tracking-wide",
  {
    variants: {
      variant: {
        default: "border-amber-300/25 bg-amber-300/10 text-amber-200",
        muted: "border-white/10 bg-white/6 text-white/70",
        success: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200",
        danger: "border-rose-400/25 bg-rose-400/10 text-rose-200",
        dark: "border-white/15 bg-white/10 text-white"
      }
    },
    defaultVariants: {
      variant: "default"
    }
  }
);

export function Badge({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
