/**
 * useToast — Global toast notification composable
 *
 * Module-level reactive state, shared by all callers.
 * Usage:
 *   const { show } = useToast()
 *   show("Bot reconnected", "success")
 *   show("Failed to fetch agents", "error", 5000)
 */

import { reactive } from "vue";

export interface Toast {
  id: number;
  message: string;
  type: "success" | "error" | "warning" | "info";
  duration: number;
}

const toasts = reactive<Toast[]>([]);
let nextId = 0;

export function useToast() {
  function show(
    message: string,
    type: Toast["type"] = "info",
    duration = 3000
  ) {
    const id = nextId++;
    toasts.push({ id, message, type, duration });
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration);
    }
    return id;
  }

  function dismiss(id: number) {
    const idx = toasts.findIndex((t) => t.id === id);
    if (idx >= 0) toasts.splice(idx, 1);
  }

  function clear() {
    toasts.splice(0, toasts.length);
  }

  // Convenience shorthands
  function success(msg: string, dur?: number) {
    return show(msg, "success", dur);
  }
  function error(msg: string, dur?: number) {
    return show(msg, "error", dur);
  }
  function warning(msg: string, dur?: number) {
    return show(msg, "warning", dur);
  }
  function info(msg: string, dur?: number) {
    return show(msg, "info", dur);
  }

  return { toasts, show, dismiss, clear, success, error, warning, info };
}