"use client";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "./utils";

type Size = "sm" | "md" | "lg";
const heights = {
  sm: "h-ds-control-sm",
  md: "h-ds-control-md",
  lg: "h-ds-control-lg",
};
type InputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> & {
  size?: Size;
  invalid?: boolean;
};
export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input({ size = "md", invalid, className, ...props }, ref) {
    return (
      <input
        {...props}
        ref={ref}
        data-slot="dm-input"
        data-size={size}
        data-variant="default"
        aria-invalid={invalid ? true : props["aria-invalid"]}
        className={cn(
          "dm-ui-input w-full rounded-ds-md border border-control-border bg-canvas px-3 text-body-sm text-ink",
          heights[size],
          className,
        )}
      />
    );
  },
);
export const Checkbox = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(function Checkbox(props, ref) {
  return (
    <input
      {...props}
      ref={ref}
      type="checkbox"
      data-slot="dm-checkbox"
      data-variant="default"
      data-size="sm"
      className={cn("dm-ui-checkbox size-4 accent-primary", props.className)}
    />
  );
});
export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
    size?: Size;
    invalid?: boolean;
    maxRows?: number;
  }
>(function Textarea(
  { size = "md", invalid, maxRows = 10, rows = 3, className, ...props },
  forwarded,
) {
  const ref = React.useRef<HTMLTextAreaElement | null>(null);
  const fit = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.resize = "none";
    el.style.height = "auto";
    const style = getComputedStyle(el);
    const line =
      Number.parseFloat(style.lineHeight) ||
      Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue(
          "--ds-typography-body-sm-lineHeight",
        ),
      );
    const padding =
      Number.parseFloat(style.paddingTop) +
      Number.parseFloat(style.paddingBottom) +
      Number.parseFloat(style.borderTopWidth) +
      Number.parseFloat(style.borderBottomWidth);
    el.style.height = `${Math.min(Math.max(el.scrollHeight, rows * line + padding), Math.max(rows, maxRows) * line + padding)}px`;
  }, [rows, maxRows]);
  React.useLayoutEffect(fit, [fit, props.value]);
  return (
    <textarea
      {...props}
      rows={rows}
      data-slot="dm-textarea"
      data-variant="default"
      data-size={size}
      aria-invalid={invalid ? true : props["aria-invalid"]}
      ref={(node) => {
        ref.current = node;
        if (typeof forwarded === "function") forwarded(node);
        else if (forwarded) forwarded.current = node;
      }}
      className={cn(
        "dm-ui-input w-full rounded-ds-md border border-control-border bg-canvas px-3 py-3 text-body-sm text-ink",
        className,
      )}
      onInput={(event) => {
        fit();
        props.onInput?.(event);
      }}
    />
  );
});
export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
  className,
  ...props
}: Omit<React.LabelHTMLAttributes<HTMLLabelElement>, "children"> & {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  children: React.ReactNode;
}) {
  const generated = React.useId();
  const first = React.Children.toArray(children).find(
    (child) =>
      React.isValidElement<{
        id?: string;
        value?: unknown;
        checked?: boolean;
        defaultValue?: unknown;
      }>(child) &&
      ([Input, Textarea, Checkbox, Select].includes(
        child.type as typeof Input,
      ) ||
        "value" in child.props ||
        "checked" in child.props),
  );
  const childId = React.isValidElement<{ id?: string }>(first)
    ? first.props.id
    : undefined;
  const id = htmlFor ?? childId ?? generated;
  let assigned = false;
  const content = React.Children.map(children, (child) => {
    if (
      React.isValidElement<{
        id?: string;
        "aria-describedby"?: string;
        invalid?: boolean;
        "aria-invalid"?: React.AriaAttributes["aria-invalid"];
      }>(child) &&
      !assigned &&
      React.isValidElement(first) &&
      child.type === first.type
    ) {
      assigned = true;
      return React.cloneElement(child, {
        id: child.props.id ?? id,
        "aria-describedby":
          [
            child.props["aria-describedby"],
            error ? `${id}-error` : null,
            hint ? `${id}-hint` : null,
          ]
            .filter(Boolean)
            .join(" ") || undefined,
        "aria-invalid": error ? true : child.props["aria-invalid"],
      });
    }
    return child;
  });
  if (label)
    return (
      <div
        data-slot="dm-field"
        className={cn(
          "dm-ui-field grid gap-2 text-body-sm text-ink",
          className,
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <label htmlFor={id} className="font-medium">
            {label}
          </label>
          {hint && (
            <span id={`${id}-hint`} className="text-caption text-body">
              {hint}
            </span>
          )}
        </div>
        {content}
        {error && (
          <span
            id={`${id}-error`}
            role="alert"
            className="text-body-sm text-error-deep"
          >
            {error}
          </span>
        )}
      </div>
    );
  return (
    <label
      {...props}
      htmlFor={id}
      data-slot="dm-field"
      className={cn("dm-ui-field grid gap-2 text-body-sm text-ink", className)}
    >
      {label && (
        <span className="flex items-center justify-between gap-2 font-medium">
          {label}
          {hint && (
            <span
              id={`${id}-hint`}
              className="text-caption font-normal text-body"
            >
              {hint}
            </span>
          )}
        </span>
      )}
      {content}
      {error && (
        <span
          id={`${id}-error`}
          role="alert"
          className="text-body-sm text-error-deep"
        >
          {error}
        </span>
      )}
    </label>
  );
}
type SelectProps = Omit<
  React.SelectHTMLAttributes<HTMLSelectElement>,
  "size" | "onChange"
> & {
  size?: Size;
  invalid?: boolean;
  onChange?: React.ChangeEventHandler<HTMLSelectElement>;
};
function options(
  children: React.ReactNode,
): { value: string; text: React.ReactNode; disabled: boolean }[] {
  return React.Children.toArray(children).flatMap((child) =>
    React.isValidElement<{
      value?: string;
      disabled?: boolean;
      children?: React.ReactNode;
    }>(child)
      ? child.type === React.Fragment
        ? options(child.props.children)
        : [
            {
              value: String(child.props.value ?? ""),
              text: child.props.children,
              disabled: !!child.props.disabled,
            },
          ]
      : [],
  );
}
export function Select({
  children,
  value,
  defaultValue,
  onChange,
  size = "md",
  invalid,
  className,
  id,
  name,
  disabled,
  required,
  "aria-label": label,
  "aria-describedby": description,
  ...rest
}: SelectProps) {
  const choices = options(children);
  let emptyValue = "__empty__";
  while (choices.some((option) => option.value === emptyValue))
    emptyValue += "_";
  const toRadix = (v: string) => (v === "" ? emptyValue : v);
  return (
    <SelectPrimitive.Root
      value={value === undefined ? undefined : String(value)}
      defaultValue={
        defaultValue === undefined ? undefined : String(defaultValue)
      }
      onValueChange={(v) =>
        onChange?.({
          target: { value: v === emptyValue ? "" : v },
          currentTarget: { value: v === emptyValue ? "" : v },
        } as React.ChangeEvent<HTMLSelectElement>)
      }
      name={name}
      disabled={disabled}
      required={required}
    >
      <SelectPrimitive.Trigger
        id={id}
        aria-label={label}
        aria-describedby={description}
        aria-invalid={invalid ? true : rest["aria-invalid"]}
        data-slot="dm-select"
        data-variant="default"
        data-size={size}
        className={cn(
          "dm-ui-input flex w-full items-center justify-between gap-2 rounded-ds-md border border-control-border bg-canvas px-3 text-body-sm text-ink",
          heights[size],
          className,
        )}
      >
        <SelectPrimitive.Value
          placeholder={choices.find((option) => option.value === "")?.text}
        />
        <SelectPrimitive.Icon>
          <ChevronDown className="size-4" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          className="dm-ui-menu z-50 max-h-80 min-w-40 rounded-ds-md border border-hairline bg-canvas p-1 text-body-sm text-ink shadow-ds-level-3"
        >
          <SelectPrimitive.Viewport>
            {choices.map((o) => (
              <SelectPrimitive.Item
                key={o.value}
                data-value={o.value}
                value={toRadix(o.value)}
                disabled={o.disabled}
                className="dm-ui-menu-item flex cursor-default items-center justify-between gap-3 rounded-ds-md px-3 py-2 outline-none"
              >
                <SelectPrimitive.ItemText>{o.text}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator>
                  <Check className="size-4" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
export function InputGroup({
  prefix,
  suffix,
  children,
}: {
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      data-slot="dm-input-group"
      className="dm-ui-input-group flex items-center gap-2 rounded-ds-md border border-control-border bg-canvas px-3"
    >
      {prefix}
      {children}
      {suffix}
    </div>
  );
}
