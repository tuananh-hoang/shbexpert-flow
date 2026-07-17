import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SHBExpert Flow",
  description: "AI Credit Intelligence Dashboard — Credit Officer workspace",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
