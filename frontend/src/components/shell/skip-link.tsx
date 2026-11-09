"use client";

export function SkipLink() {
  return (
    <a
      className="ds-skip-link"
      href="#main-content"
      onClick={() => {
        window.requestAnimationFrame(() => document.getElementById("main-content")?.focus());
      }}
    >
      Skip to main content
    </a>
  );
}
