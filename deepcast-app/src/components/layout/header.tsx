"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"

const navLinks = [
  { href: "/episodes", label: "エピソード" },
  { href: "/library", label: "ライブラリ" },
]

export function Header() {
  const [menuOpen, setMenuOpen] = useState(false)
  const pathname = usePathname()

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        {/* Logo */}
        <Link href="/" className="font-serif text-xl font-bold tracking-tight">
          <span className="text-[#3a8a44]">Deep</span>Cast AI
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-6 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`text-sm font-medium transition-colors hover:text-[#3a8a44] ${
                pathname.startsWith(link.href)
                  ? "text-[#3a8a44]"
                  : "text-muted-foreground"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <Link
            href="/auth/login"
            className="rounded-md bg-[#3a8a44] px-4 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            ログイン
          </Link>
        </nav>

        {/* Mobile hamburger */}
        <button
          type="button"
          className="flex size-9 items-center justify-center rounded-md text-foreground md:hidden"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="メニューを開く"
        >
          {menuOpen ? (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <nav className="border-t border-border bg-background px-4 pb-4 pt-2 md:hidden">
          <ul className="flex flex-col gap-2">
            {navLinks.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  onClick={() => setMenuOpen(false)}
                  className={`block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    pathname.startsWith(link.href)
                      ? "bg-[#3a8a44]/10 text-[#3a8a44]"
                      : "text-foreground hover:bg-muted"
                  }`}
                >
                  {link.label}
                </Link>
              </li>
            ))}
            <li>
              <Link
                href="/auth/login"
                onClick={() => setMenuOpen(false)}
                className="block rounded-md bg-[#3a8a44] px-3 py-2 text-center text-sm font-medium text-white transition-opacity hover:opacity-90"
              >
                ログイン
              </Link>
            </li>
          </ul>
        </nav>
      )}
    </header>
  )
}
