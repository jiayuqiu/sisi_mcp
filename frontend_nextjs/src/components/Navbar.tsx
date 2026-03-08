"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Ship, MessageSquare, BarChart2 } from "lucide-react";
import { clsx } from "clsx";

const navLinks = [
  { href: "/workflow", label: "Workflow",   icon: BarChart2 },
];

export default function Navbar() {
  const pathname = usePathname();

  return (
    <header className="flex-shrink-0 h-14 bg-navy-800 border-b border-navy-700 flex items-center px-6 gap-8 z-50">
      {/* Brand */}
      <Link href="/" className="flex items-center gap-2 group">
        <div className="w-8 h-8 rounded-lg bg-teal-500/20 border border-teal-500/40 flex items-center justify-center group-hover:border-teal-400 transition-colors">
          <Ship className="w-4 h-4 text-teal-400" />
        </div>
        <span className="font-semibold text-white tracking-wide text-sm">
          Sisi<span className="text-teal-400">MCP</span>
        </span>
      </Link>

      {/* Divider */}
      <div className="h-5 w-px bg-navy-600" />

      {/* Nav links */}
      <nav className="flex items-center gap-1">
        {navLinks.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-150",
                active
                  ? "bg-teal-500/15 text-teal-400 border border-teal-500/30"
                  : "text-slate-400 hover:text-slate-200 hover:bg-navy-700"
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Right side badge */}
      <div className="ml-auto flex items-center gap-2">
        <span className="text-xs text-slate-500 font-mono">maritime · anomaly detection</span>
        <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
      </div>
    </header>
  );
}
