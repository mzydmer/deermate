"use client";
import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import { LoaderCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { cn } from "./utils";

type Variant = "primary" | "secondary" | "ghost" | "link" | "danger";
type Tone = "neutral" | "muted" | "link" | "danger";
export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  tone?: Tone;
  loading?: boolean;
  asChild?: boolean;
};
const shape = cva(
  "dm-ui-button relative inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-ds-md border text-button-md font-medium",
  {
    variants: {
      variant: {
        primary: "border-primary bg-primary",
        secondary: "border-control-border bg-canvas",
        ghost: "border-transparent bg-transparent",
        link: "border-transparent bg-transparent",
        danger: "border-error-deep bg-error-deep",
      },
      size: {
        sm: "h-ds-control-sm px-3",
        md: "h-ds-control-md px-4",
        lg: "h-ds-control-lg px-6",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);
const textTone: Record<Tone, string> = {
  neutral: "text-ink",
  muted: "text-body",
  link: "text-link-deep",
  danger: "text-error-deep",
};
export function Button({
  variant = "secondary",
  size = "md",
  tone,
  loading = false,
  asChild = false,
  disabled,
  children,
  className,
  type = "button",
  ...props
}: ButtonProps) {
  const stableLabel = React.useRef(children);
  React.useLayoutEffect(() => {
    if (!loading) stableLabel.current = children;
  }, [children, loading]);
  const Comp = asChild ? Slot : "button";
  const unavailable = disabled === true || loading;
  const slotted =
    asChild &&
    unavailable &&
    React.isValidElement<React.HTMLAttributes<HTMLElement>>(children)
      ? React.cloneElement(children, {
          tabIndex: -1,
          onClick: (event) => {
            event.preventDefault();
            event.stopPropagation();
          },
          onKeyDown: (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              event.stopPropagation();
            }
          },
        })
      : children;
  const color = tone
    ? textTone[tone]
    : variant === "primary" || variant === "danger"
      ? "text-on-primary"
      : variant === "link"
        ? textTone.link
        : textTone.neutral;
  return (
    <Comp
      {...props}
      type={asChild ? undefined : type}
      data-slot="dm-button"
      data-variant={variant}
      data-size={size}
      data-tone={tone ?? "default"}
      aria-busy={loading ? true : props["aria-busy"]}
      aria-disabled={asChild && (disabled || loading) ? true : undefined}
      disabled={!asChild && (disabled || loading) ? true : undefined}
      className={cn(shape({ variant, size }), color, className)}
      onClick={(event) => {
        if (disabled || loading) {
          event.preventDefault();
          return;
        }
        props.onClick?.(event as React.MouseEvent<HTMLButtonElement>);
      }}
    >
      {loading && !asChild ? (
        <>
          <LoaderCircle
            data-slot="dm-spinner"
            className="dm-ui-spinner absolute left-1 size-3"
            aria-hidden="true"
          />
          {stableLabel.current}
        </>
      ) : (
        slotted
      )}
    </Comp>
  );
}
export type IconButtonProps = Omit<
  ButtonProps,
  "children" | "aria-label" | "size" | "variant" | "asChild"
> & {
  href?: string;
  label: string;
  icon: React.ReactNode;
  size?: "sm" | "md";
  variant?: "default" | "ghost";
};
export function IconButton({
  label,
  href,
  icon,
  size = "sm",
  variant = "ghost",
  className,
  loading,
  disabled,
  ...props
}: IconButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          {...props}
          asChild={!!href}
          disabled={disabled === true || loading}
          aria-busy={loading ? true : props["aria-busy"]}
          aria-label={label}
          variant={variant === "default" ? "secondary" : "ghost"}
          size={size}
          className={cn("dm-ui-icon-button p-0", className)}
        >
          {href ? (
            <Link href={href} aria-label={label}>
              {icon}
            </Link>
          ) : loading ? (
            <LoaderCircle
              data-slot="dm-spinner"
              className="dm-ui-spinner size-4"
              aria-hidden="true"
            />
          ) : (
            icon
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function SendButton({
  label,
  icon,
  loading,
  disabled,
  size = "md",
  className,
  ...props
}: Omit<IconButtonProps, "variant" | "href">) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          {...props}
          size={size}
          variant="primary"
          aria-label={label}
          aria-busy={loading ? true : undefined}
          disabled={disabled === true || loading}
          className={cn("dm-ui-icon-button rounded-ds-full p-0", className)}
        >
          {loading ? (
            <LoaderCircle
              data-slot="dm-spinner"
              className="dm-ui-spinner size-4"
              aria-hidden="true"
            />
          ) : (
            icon
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
