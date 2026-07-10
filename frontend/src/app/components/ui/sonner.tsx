"use client";

import { Toaster as Sonner, ToasterProps } from "sonner";
import { useTheme } from "../Layout";

const Toaster = ({ ...props }: ToasterProps) => {
  // Follow the app-wide dark/light toggle (Layout ThemeProvider) so toasts
  // match the rest of the UI instead of tracking next-themes separately.
  const { dark } = useTheme();

  return (
    <Sonner
      theme={(dark ? "dark" : "light") as ToasterProps["theme"]}
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
