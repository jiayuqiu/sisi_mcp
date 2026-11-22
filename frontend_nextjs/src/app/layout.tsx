import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import ChatWidget from "@/components/ChatWidget";
import { THEME_STORAGE_KEY } from "@/lib/theme";

const initializeTheme = `
  try {
    if (localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)}) === "light") {
      document.documentElement.dataset.theme = "light";
    }
  } catch {}
`;

export const metadata: Metadata = {
  title: "SisiMCP — Maritime Traffic Analysis",
  description: "Maritime traffic anomaly detection for Malacca Strait and Bab-el-Mandeb",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className="group/theme h-full" suppressHydrationWarning>
      <head>
        {/* Apply the saved appearance before the page paints. */}
        <script dangerouslySetInnerHTML={{ __html: initializeTheme }} />
      </head>
      <body className="h-full flex flex-col bg-canvas">
        <Navbar />
        <main className="flex-1 flex flex-col overflow-hidden">
          {children}
        </main>
        <ChatWidget />
      </body>
    </html>
  );
}
