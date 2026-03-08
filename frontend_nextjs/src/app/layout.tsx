import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import ChatWidget from "@/components/ChatWidget";

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
    <html lang="zh-CN" className="h-full">
      <body className="h-full flex flex-col bg-navy-900">
        <Navbar />
        <main className="flex-1 flex flex-col overflow-hidden">
          {children}
        </main>
        <ChatWidget />
      </body>
    </html>
  );
}
