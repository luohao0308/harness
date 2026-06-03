import type { ReactNode } from "react";
import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

type VirtualListProps<T> = {
  items: T[];
  estimateSize?: number;
  height?: number;
  renderItem: (item: T, index: number) => ReactNode;
};

export function VirtualList<T>({
  items,
  estimateSize = 56,
  height = 420,
  renderItem,
}: VirtualListProps<T>) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const shouldRenderAll =
    items.length <= 50 || typeof window === "undefined" || !("ResizeObserver" in window);
  const rowVirtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateSize,
    overscan: 8,
  });

  if (shouldRenderAll) {
    return (
      <div className="overflow-auto" style={{ maxHeight: height }}>
        {items.map((item, index) => (
          <div key={index}>{renderItem(item, index)}</div>
        ))}
      </div>
    );
  }

  return (
    <div ref={parentRef} className="overflow-auto" style={{ height }}>
      <div className="relative w-full" style={{ height: rowVirtualizer.getTotalSize() }}>
        {rowVirtualizer.getVirtualItems().map((virtualRow) => (
          <div
            key={virtualRow.key}
            className="absolute left-0 top-0 w-full"
            style={{
              height: virtualRow.size,
              transform: `translateY(${virtualRow.start}px)`,
            }}
          >
            {renderItem(items[virtualRow.index], virtualRow.index)}
          </div>
        ))}
      </div>
    </div>
  );
}
