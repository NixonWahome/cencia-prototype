import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, wsUrl } from "./client";
import type { Alert, LiveMessage, SimStatus } from "./types";

type Channel = "tick" | "alerts" | "scans" | "integrity" | "attacks";

export interface Toast {
  id: number;
  tone: "critical" | "high" | "medium" | "info" | "good";
  title: string;
  body?: string;
  href?: string;
}

interface LiveState {
  connected: boolean;
  sim: SimStatus | null;
  versions: Record<Channel, number>;
  toasts: Toast[];
  sms: Alert | null;
  lastMessage: LiveMessage | null;
  pushToast: (t: Omit<Toast, "id">) => void;
  dismissToast: (id: number) => void;
  dismissSms: () => void;
}

const LiveContext = createContext<LiveState | null>(null);

const ZERO: Record<Channel, number> = { tick: 0, alerts: 0, scans: 0, integrity: 0, attacks: 0 };

export function LiveProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [sim, setSim] = useState<SimStatus | null>(null);
  const [versions, setVersions] = useState(ZERO);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [sms, setSms] = useState<Alert | null>(null);
  const [lastMessage, setLastMessage] = useState<LiveMessage | null>(null);
  const nextId = useRef(1);

  const bump = useCallback((...channels: Channel[]) => {
    setVersions((v) => {
      const next = { ...v };
      for (const c of channels) next[c] += 1;
      return next;
    });
  }, []);

  const dismissToast = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const pushToast = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = nextId.current++;
      setToasts((ts) => [...ts.slice(-3), { ...t, id }]);
      window.setTimeout(() => dismissToast(id), 7000);
    },
    [dismissToast],
  );

  const handle = useCallback(
    (msg: LiveMessage) => {
      setLastMessage(msg);
      switch (msg.type) {
        case "hello":
          setSim(msg);
          break;
        case "tick":
          setSim((s) => (s ? { ...s, sim_time: msg.sim_time, last_interval: msg.ts } : s));
          bump("tick");
          break;
        case "alert": {
          const a = msg.alert;
          const tone = a.severity === "critical" || a.severity === "high" ? a.severity : "medium";
          pushToast({ tone, title: a.title, body: `${a.rule_id} · ${a.site_id}`, href: `/alerts?id=${a.id}` });
          if (a.severity === "critical" || a.severity === "high") setSms(a);
          bump("alerts");
          break;
        }
        case "alert_updated":
          bump("alerts");
          break;
        case "attack":
          pushToast({ tone: "info", title: `Attack launched: ${msg.attack.label ?? msg.attack.type}`, body: msg.attack.note });
          bump("attacks", "alerts", "tick");
          break;
        case "integrity_failure":
          bump("integrity", "alerts");
          break;
        case "scan_progress":
        case "scan_complete":
        case "finding_remediated":
          bump("scans");
          break;
        case "reset":
          pushToast({ tone: "good", title: "Demo reset", body: "Attacks, alerts and scans cleared." });
          setSms(null);
          bump("tick", "alerts", "scans", "integrity", "attacks");
          break;
      }
    },
    [bump, pushToast],
  );

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: number | undefined;
    let stopped = false;
    let attempt = 0;

    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        attempt = 0;
        setConnected(true);
        bump("tick", "alerts", "scans", "integrity", "attacks"); // resync after a reconnect
      };
      ws.onmessage = (e) => handle(JSON.parse(e.data) as LiveMessage);
      ws.onclose = () => {
        setConnected(false);
        if (!stopped) retry = window.setTimeout(connect, Math.min(1000 * 2 ** attempt++, 8000));
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    // Keep the clock fresh even if the socket is down.
    api.get<SimStatus>("/api/sim").then(setSim).catch(() => undefined);
    return () => {
      stopped = true;
      window.clearTimeout(retry);
      ws?.close();
    };
  }, [handle, bump]);

  return (
    <LiveContext.Provider
      value={{ connected, sim, versions, toasts, sms, lastMessage, pushToast, dismissToast, dismissSms: () => setSms(null) }}
    >
      {children}
    </LiveContext.Provider>
  );
}

export function useLive(): LiveState {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error("useLive outside LiveProvider");
  return ctx;
}

/** Fetch `path` and refetch whenever any of the given live channels change. */
export function useApi<T>(path: string | null, channels: Channel[] = []) {
  const { versions } = useLive();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [manual, setManual] = useState(0);
  const key = channels.map((c) => versions[c]).join(",");

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setLoading(true);
    api
      .get<T>(path)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [path, key, manual]);

  return { data, error, loading, reload: () => setManual((n) => n + 1), setData };
}
