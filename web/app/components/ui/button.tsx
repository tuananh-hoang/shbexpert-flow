import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import { cn } from "@/app/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-full text-sm font-semibold whitespace-nowrap transition-all duration-150 outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        /* SHB primary CTA: white bg + orange border + orange text → peach bg on hover */
        default:   "border border-[var(--color-orange-600)] bg-white text-[var(--color-orange-600)] hover:bg-[var(--color-orange-100)] hover:text-[var(--color-orange-500)]",
        /* Filled orange — used for truly primary actions like "Gửi", "Chạy phân tích" */
        primary:   "bg-[var(--color-orange-600)] text-white hover:bg-[var(--brand-primary-hover)]",
        secondary: "border border-[var(--color-navy-300)] bg-white text-[var(--color-navy-700)] hover:bg-[var(--color-navy-50)]",
        outline:   "border border-[var(--color-orange-600)] bg-white text-[var(--color-orange-600)] hover:bg-[var(--color-orange-100)] hover:text-[var(--color-orange-500)]",
        ghost:     "bg-transparent text-[var(--color-navy-700)] hover:bg-[var(--color-gray-100)]",
        link:      "text-primary",
      },
      size: {
        default: "h-9 px-5 py-2",
        sm:      "h-8 px-4 text-xs",
        lg:      "h-10 px-7",
        xs:      "h-6 px-3 text-xs",
        icon:    "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />
  );
}

export { Button, buttonVariants };
