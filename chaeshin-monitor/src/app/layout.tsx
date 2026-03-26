import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chaeshin Monitor",
  description: "CBR Case Store Monitoring — Tool Graph Viewer",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        {children}
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
