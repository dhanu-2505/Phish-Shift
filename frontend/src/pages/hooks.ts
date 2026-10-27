import { useOutletContext } from "react-router-dom";
import type { SystemHealth } from "../api";

export function useSystemHealth(): { health: SystemHealth | null } {
  return useOutletContext<{ health: SystemHealth | null }>();
}
