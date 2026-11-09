"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  panel: ReactNode;
  disabled?: boolean;
}

export function Tabs({
  items,
  selectedId,
  onSelect,
  label,
}: {
  items: TabItem[];
  selectedId: string;
  onSelect: (id: string) => void;
  label: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const enabled = items.map((item, index) => ({ item, index })).filter(({ item }) => !item.disabled);
  const selected = items.find((item) => item.id === selectedId) ?? enabled[0]?.item;

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, currentIndex: number) {
    const enabledPosition = enabled.findIndex(({ index }) => index === currentIndex);
    if (enabledPosition < 0) return;
    let nextPosition = enabledPosition;
    if (event.key === "ArrowRight") nextPosition = (enabledPosition + 1) % enabled.length;
    else if (event.key === "ArrowLeft") nextPosition = (enabledPosition - 1 + enabled.length) % enabled.length;
    else if (event.key === "Home") nextPosition = 0;
    else if (event.key === "End") nextPosition = enabled.length - 1;
    else return;
    event.preventDefault();
    refs.current[enabled[nextPosition].index]?.focus();
  }

  if (!selected) return null;

  return (
    <div className="ds-tabs">
      <div className="ds-tab-list" role="tablist" aria-label={label}>
        {items.map((item, index) => (
          <button
            key={item.id}
            ref={(node) => { refs.current[index] = node; }}
            id={`tab-${item.id}`}
            className="ds-tab"
            type="button"
            role="tab"
            aria-selected={selected.id === item.id}
            aria-controls={`panel-${item.id}`}
            tabIndex={selected.id === item.id ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onSelect(item.id)}
            onKeyDown={(event) => moveFocus(event, index)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        id={`panel-${selected.id}`}
        role="tabpanel"
        aria-labelledby={`tab-${selected.id}`}
        tabIndex={0}
      >
        {selected.panel}
      </div>
    </div>
  );
}
