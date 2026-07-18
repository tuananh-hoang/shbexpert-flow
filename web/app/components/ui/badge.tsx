import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import { cn } from "@/app/lib/utils";

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        destructive: "bg-destructive text-white",
        outline: "border-border text-foreground",
        success: "bg-[var(--status-success-bg)] text-[var(--status-success-fg)]",
        warning: "bg-[var(--status-warning-bg)] text-[var(--status-warning-fg)]",
        danger:  "bg-[var(--status-danger-bg)]  text-[var(--status-danger-fg)]",
        navy:    "bg-[var(--color-navy-50)]      text-[var(--color-navy-700)]",
        orange:  "bg-[var(--color-orange-100)]   text-[var(--color-orange-800)]",
        muted:   "bg-muted text-muted-foreground border border-border",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span";
  return (
    <Comp className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
