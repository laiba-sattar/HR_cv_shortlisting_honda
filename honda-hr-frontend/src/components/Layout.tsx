import React from "react";
import AppHeader from "./AppHeader";

/**
 * Shell for the secondary pages (History / Administration / Help).
 * The Workspace renders its own full-width layout.
 */
const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="page-ground flex min-h-screen flex-col">
    <AppHeader />
    <main className="mx-auto w-full max-w-shell flex-1 px-5 py-8 lg:px-8 lg:py-10">
      <div className="animate-in">{children}</div>
    </main>
    <footer className="border-t border-cream-200 px-5 py-5 lg:px-8">
      <div className="mx-auto flex max-w-shell flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-400">
        <span className="flex items-center gap-2 font-mono text-2xs uppercase tracking-[0.12em] text-ink-500">
          <span aria-hidden className="h-3 w-[3px] rounded-full bg-honda-red" />
          Honda Atlas Cars Pakistan
        </span>
        <span aria-hidden className="text-cream-300">|</span>
        <span>This system ranks and explains; a person makes the hiring decision.</span>
      </div>
    </footer>
  </div>
);

export default Layout;
