import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "../../lib/utils";

export type MenuSelectOption = {
  value: string;
  label: ReactNode;
  description?: ReactNode;
  meta?: ReactNode;
  leading?: ReactNode;
  group?: ReactNode;
  disabled?: boolean;
};

export type MenuSelectProps = {
  ariaLabel: string;
  value: string;
  options: MenuSelectOption[];
  onChange: (value: string) => void;
  placeholder?: ReactNode;
  leading?: ReactNode;
  disabled?: boolean;
  openRequestSeq?: number;
  placement?: "bottom" | "top";
  size?: "default" | "compact";
  showSelectedDescription?: boolean;
  className?: string;
  buttonClassName?: string;
  menuClassName?: string;
};

export function MenuSelect({
  ariaLabel,
  value,
  options,
  onChange,
  placeholder = "-",
  leading,
  disabled = false,
  openRequestSeq,
  placement = "bottom",
  size = "default",
  showSelectedDescription = true,
  className,
  buttonClassName,
  menuClassName,
}: MenuSelectProps) {
  const baseId = useId();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const selected = useMemo(
    () => options.find((option) => option.value === value) ?? null,
    [options, value],
  );
  const selectedIndex = useMemo(
    () => options.findIndex((option) => option.value === value),
    [options, value],
  );

  const findNextEnabledIndex = (startIndex: number) => {
    if (options.length === 0) return -1;
    for (let offset = 1; offset <= options.length; offset += 1) {
      const index = (startIndex + offset) % options.length;
      if (!options[index]?.disabled) return index;
    }
    return -1;
  };

  const findPreviousEnabledIndex = (startIndex: number) => {
    if (options.length === 0) return -1;
    for (let offset = 1; offset <= options.length; offset += 1) {
      const index = (startIndex - offset + options.length) % options.length;
      if (!options[index]?.disabled) return index;
    }
    return -1;
  };

  const findFirstEnabledIndex = () => options.findIndex((option) => !option.disabled);
  const findLastEnabledIndex = () => {
    for (let index = options.length - 1; index >= 0; index -= 1) {
      if (!options[index]?.disabled) return index;
    }
    return -1;
  };

  const closeMenu = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const commitSelection = (optionValue: string) => {
    onChange(optionValue);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleTriggerKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    if (!open) {
      setOpen(true);
      const fallback = selectedIndex >= 0 && !options[selectedIndex]?.disabled ? selectedIndex : findFirstEnabledIndex();
      setActiveIndex(fallback);
      return;
    }
    if (event.key === "ArrowDown") {
      const fallback = selectedIndex >= 0 && !options[selectedIndex]?.disabled ? selectedIndex : findFirstEnabledIndex();
      setActiveIndex(fallback);
      return;
    }
    if (event.key === "ArrowUp") {
      const fallback = selectedIndex >= 0 && !options[selectedIndex]?.disabled ? selectedIndex : findLastEnabledIndex();
      setActiveIndex(fallback);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      const next = activeIndex >= 0 ? options[activeIndex] : selected ?? null;
      if (next && !next.disabled) {
        commitSelection(next.value);
      }
    }
  };

  const handleMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!open) return;
    switch (event.key) {
      case "Escape":
        event.preventDefault();
        closeMenu();
        return;
      case "ArrowDown": {
        event.preventDefault();
        const nextIndex =
          activeIndex < 0
            ? findFirstEnabledIndex()
            : findNextEnabledIndex(activeIndex);
        if (nextIndex >= 0) setActiveIndex(nextIndex);
        return;
      }
      case "ArrowUp": {
        event.preventDefault();
        const previousIndex =
          activeIndex < 0
            ? findLastEnabledIndex()
            : findPreviousEnabledIndex(activeIndex);
        if (previousIndex >= 0) setActiveIndex(previousIndex);
        return;
      }
      case "Home":
        event.preventDefault();
        setActiveIndex(findFirstEnabledIndex());
        return;
      case "End":
        event.preventDefault();
        setActiveIndex(findLastEnabledIndex());
        return;
      case "Enter":
      case " ":
        if (activeIndex >= 0 && !options[activeIndex]?.disabled) {
          event.preventDefault();
          commitSelection(options[activeIndex].value);
        }
        return;
      default:
        return;
    }
  };

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointer = (event: MouseEvent | TouchEvent) => {
      const element = containerRef.current;
      if (!element) {
        setOpen(false);
        return;
      }
      const target = event.target;
      if (target instanceof Node && element.contains(target)) {
        return;
      }
      setOpen(false);
    };

    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("touchstart", handlePointer);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("touchstart", handlePointer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const fallback = selectedIndex >= 0 && !options[selectedIndex]?.disabled ? selectedIndex : findFirstEnabledIndex();
    setActiveIndex(fallback);
    window.requestAnimationFrame(() => menuRef.current?.focus());
  }, [open, options, selectedIndex]);

  useEffect(() => {
    if (openRequestSeq === undefined || openRequestSeq <= 0 || disabled) {
      return;
    }
    setOpen(true);
  }, [disabled, openRequestSeq]);

  const selectedLabel = selected?.label ?? placeholder;
  const selectedDescription = showSelectedDescription ? selected?.description : null;
  const selectedLeading = leading ?? selected?.leading;
  const selectedMeta = selected?.meta;
  const selectedLabelText = typeof selectedLabel === "string" ? selectedLabel : null;
  const ariaName = selectedLabelText ? `${ariaLabel}：${selectedLabelText}` : ariaLabel;

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaName}
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={handleTriggerKeyDown}
        className={cn(
          "flex w-full items-center rounded-2xl border border-slate-200 bg-white text-left shadow-sm transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50",
          size === "compact" ? "gap-2 px-2.5 py-1.5" : "gap-3 px-4 py-3",
          buttonClassName,
        )}
      >
        {selectedLeading ? (
          <span
            className={cn(
              "flex shrink-0 items-center justify-center bg-slate-100 text-slate-600",
              size === "compact" ? "h-6 w-6 rounded-lg" : "h-8 w-8 rounded-xl",
            )}
          >
            {selectedLeading}
          </span>
        ) : null}
        <span className="min-w-0 flex-1">
          <span
            className={cn(
              "block truncate font-semibold text-slate-900",
              size === "compact" ? "text-xs" : "text-sm",
            )}
          >
            {selectedLabel}
          </span>
          {selectedDescription ? (
            <span className="mt-0.5 block truncate text-[11px] leading-4 text-slate-500">
              {selectedDescription}
            </span>
          ) : null}
        </span>
        {selectedMeta ? (
          <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
            {selectedMeta}
          </span>
        ) : null}
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
      </button>

      {open && !disabled && (
        <div
          ref={menuRef}
          role="listbox"
          aria-label={ariaLabel}
          tabIndex={-1}
          aria-activedescendant={activeIndex >= 0 ? `${baseId}-option-${activeIndex}` : undefined}
          onKeyDown={handleMenuKeyDown}
          className={cn(
            "absolute left-0 z-30 max-h-80 w-full overflow-auto rounded-2xl border border-slate-200 bg-white p-1 shadow-none",
            placement === "top" ? "bottom-full mb-2 top-auto" : "top-full mt-2",
            menuClassName,
          )}
        >
          {options.map((option, index) => {
            const active = option.value === value;
            const highlighted = index === activeIndex;
            const previousGroup = index > 0 ? options[index - 1]?.group : null;
            const showGroup = option.group && option.group !== previousGroup;
            return (
              <div key={option.value}>
                {showGroup ? (
                  <div className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                    {option.group}
                  </div>
                ) : null}
                <div
                  id={`${baseId}-option-${index}`}
                  role="option"
                  aria-selected={active}
                  aria-disabled={option.disabled || undefined}
                  onMouseEnter={() => {
                    if (!option.disabled) {
                      setActiveIndex(index);
                    }
                  }}
                  onClick={() => {
                    if (!option.disabled) {
                      commitSelection(option.value);
                    }
                  }}
                  className={cn(
                    "flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
                    active ? "bg-slate-900 text-white" : "hover:bg-slate-50",
                    highlighted && !active && "bg-slate-100",
                    option.disabled && "cursor-not-allowed opacity-40",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                      active ? "bg-white/10 text-white" : "bg-slate-100 text-slate-600",
                    )}
                  >
                    {option.leading ? (
                      option.leading
                    ) : active ? (
                      <Check className="h-4 w-4" />
                    ) : null}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{option.label}</span>
                    {option.description ? (
                      <span
                        className={cn(
                          "mt-0.5 block truncate text-[11px] leading-4",
                          active ? "text-slate-300" : "text-slate-500",
                        )}
                      >
                        {option.description}
                      </span>
                    ) : null}
                  </span>
                  {option.meta ? (
                    <span
                      className={cn(
                        "shrink-0 rounded-full px-2 py-0.5 text-[11px]",
                        active ? "bg-white/10 text-white" : "bg-slate-100 text-slate-500",
                      )}
                    >
                      {option.meta}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
