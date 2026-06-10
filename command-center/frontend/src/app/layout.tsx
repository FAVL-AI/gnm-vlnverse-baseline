import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";

const monoFont = localFont({
  src: [
    { path: "../../public/fonts/JetBrainsMono-Regular.woff2", weight: "400", style: "normal" },
    { path: "../../public/fonts/JetBrainsMono-Medium.woff2",  weight: "500", style: "normal" },
    { path: "../../public/fonts/JetBrainsMono-Bold.woff2",    weight: "700", style: "normal" },
  ],
  variable: "--font-mono-base",
  display: "swap",
});

export const metadata: Metadata = {
  title: "FleetSafe Command Center",
  description: "Real-time benchmark orchestration for embodied AI navigation",
  authors: [{ name: "Frank Van Laarhoven" }],
  creator: "Frank Van Laarhoven",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "FleetSafe",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/icon-192.png" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${monoFont.variable} h-full`} suppressHydrationWarning>
      <body className="h-full antialiased">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
