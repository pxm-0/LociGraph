"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

type Mode = "hearth" | "meridian";

type ModeContextValue = {
  mode: Mode;
  setMode: (mode: Mode) => void;
};

const ModeContext = createContext<ModeContextValue | null>(null);

export function ModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<Mode>("hearth");

  useEffect(() => {
    const stored = window.localStorage.getItem("locigraph-mode");
    if (stored === "hearth" || stored === "meridian") {
      setModeState(stored);
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.mode = mode;
    window.localStorage.setItem("locigraph-mode", mode);
  }, [mode]);

  const value = useMemo(
    () => ({
      mode,
      setMode: setModeState
    }),
    [mode]
  );

  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
}

export function useMode() {
  const value = useContext(ModeContext);
  if (!value) {
    throw new Error("useMode must be used inside ModeProvider");
  }
  return value;
}
