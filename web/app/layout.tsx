import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "./components/Sidebar";
import { LanguageProvider } from "./lib/i18n";

export const metadata: Metadata = {
  title: "SHBExpert Flow",
  description: "AI Credit Intelligence Dashboard — Credit Officer workspace",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>
        {/* LanguageProvider sets document.documentElement.lang itself once
            mounted (see lib/i18n.tsx) — the "vi" above is just the
            pre-hydration default, matching most users' actual choice. */}
        <LanguageProvider>
          {/* Sidebar is global (Queue + every case page) — see
              web/app/components/Sidebar.tsx for why. */}
          <div className="app-layout">
            <Sidebar />
            <div className="app-content">{children}</div>
          </div>
        </LanguageProvider>
      </body>
    </html>
  );
}
