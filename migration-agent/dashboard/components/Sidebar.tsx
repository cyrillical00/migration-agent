"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Waves,
  Shield,
  ScrollText,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Inventory", href: "/inventory", icon: LayoutDashboard },
  { label: "Identity Map", href: "/identity-map", icon: Users },
  { label: "Waves", href: "/waves", icon: Waves },
  { label: "Gates", href: "/gates", icon: Shield },
  { label: "Audit Log", href: "/audit", icon: ScrollText },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-56 flex-col border-r border-border bg-card">
      <div className="flex h-14 items-center border-b border-border px-4">
        <span className="font-semibold text-sm">Migration Agent</span>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {NAV.map(({ label, href, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              pathname === href
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
