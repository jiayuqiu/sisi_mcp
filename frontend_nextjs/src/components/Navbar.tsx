"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart2, Moon, Ship, Sun } from "lucide-react";
import { clsx } from "clsx";
import { THEME_STORAGE_KEY } from "@/lib/theme";

const navLinks = [
  { href: "/workflow", label: "海峡通道专员", icon: BarChart2 },
  { href: "/workflow-port", label: "港口监测专员", icon: BarChart2 },
];

function toggleTheme() {
  const { dataset } = document.documentElement;
  const theme = dataset.theme === "light" ? "dark" : "light";
  dataset.theme = theme;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // The current page can still switch themes when storage is unavailable.
  }
}

export default function Navbar() {
  const pathname = usePathname();

  return (
    <header className="flex-shrink-0 h-14 bg-panel border-b border-divider flex items-center px-3 gap-2 sm:px-6 sm:gap-8 z-50">
      {/* Brand */}
      <Link href="/" className="flex shrink-0 items-center gap-2 group">
        <div className="w-8 h-8 rounded-lg bg-teal-500/20 border border-teal-500/40 flex items-center justify-center group-hover:border-teal-400 transition-colors">
          <Ship className="w-4 h-4 text-teal-400" />
        </div>
        <span className="font-semibold text-fg-strong tracking-wide text-sm whitespace-nowrap max-[419px]:sr-only">
          SISI<span className="text-teal-400">航运专家</span>
        </span>
      </Link>

      {/* Divider */}
      <div className="hidden sm:block h-5 w-px bg-outline" />

      {/* Nav links */}
      <nav className="flex items-center gap-1">
        {navLinks.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-2 whitespace-nowrap px-1.5 sm:px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-150",
                active
                  ? "bg-teal-500/15 text-teal-400 border border-teal-500/30"
                  : "text-fg-secondary hover:text-fg hover:bg-surface"
              )}
            >
              <Icon className="hidden sm:block w-4 h-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-4">
        <button
          type="button"
          onClick={toggleTheme}
          className="flex h-9 min-w-9 items-center justify-center rounded-lg border border-outline px-2.5 text-sm font-medium text-fg-secondary transition-colors hover:bg-surface hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-400"
        >
          <span className="flex items-center gap-2 group-data-[theme=light]/theme:hidden">
            <Sun aria-hidden="true" className="h-4 w-4" />
            <span className="sr-only sm:not-sr-only">浅色模式</span>
          </span>
          <span className="hidden items-center gap-2 group-data-[theme=light]/theme:flex">
            <Moon aria-hidden="true" className="h-4 w-4" />
            <span className="sr-only sm:not-sr-only">深色模式</span>
          </span>
        </button>
        <div className="hidden lg:flex items-center gap-2">
          <span className="text-xs text-fg-muted font-mono">maritime · anomaly detection</span>
          <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
        </div>
      </div>
    </header>
  );
}
