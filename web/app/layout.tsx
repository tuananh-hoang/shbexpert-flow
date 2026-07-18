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
        <LanguageProvider>
          <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
            <div className="app-layout">
              <Sidebar />
              <div className="app-content">{children}</div>
            </div>
          </div>
        </LanguageProvider>
      </body>
    </html>
  );
}
