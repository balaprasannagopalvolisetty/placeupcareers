import { createContext, useContext } from "react";

export const SectionActiveCtx = createContext(false);
export const useSectionActive = () => useContext(SectionActiveCtx);
