// Per-viewer look preferences (theme, text size). Browser storage is only a
// convenience here; everything works without it.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";
type Size = "normal" | "large" | "xlarge";
const SIZES: Size[] = ["normal", "large", "xlarge"];

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignore: preference just isn't remembered
  }
}

interface Prefs {
  theme: Theme;
  setTheme: (t: Theme) => void;
  size: Size;
  cycleSize: () => void;
}

const Ctx = createContext<Prefs | null>(null);

function initialTheme(): Theme {
  const saved = read("lyra-lite:theme");
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const [size, setSize] = useState<Size>(() => (SIZES.includes(read("lyra-lite:size") as Size) ? (read("lyra-lite:size") as Size) : "normal"));

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    write("lyra-lite:theme", theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.dataset.size = size;
    write("lyra-lite:size", size);
  }, [size]);

  const cycleSize = useCallback(() => setSize((s) => SIZES[(SIZES.indexOf(s) + 1) % SIZES.length]), []);
  return <Ctx.Provider value={{ theme, setTheme: setThemeState, size, cycleSize }}>{children}</Ctx.Provider>;
}

export function usePrefs(): Prefs {
  const value = useContext(Ctx);
  if (!value) throw new Error("PrefsProvider missing");
  return value;
}
