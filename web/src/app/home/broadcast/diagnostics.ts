export const BROADCAST_DIAGNOSTICS_VERSION = 'freeze-diagnostic-v1';

type BroadcastDiagnosticEvent<T = unknown> = {
  at: number;
  value: T;
};

export interface BroadcastMeasuredCall {
  label: string;
  startedAt: number;
  endedAt: number;
  durationMs: number;
  stack?: string;
  meta?: Record<string, unknown>;
}

export interface BroadcastLongTaskRecord {
  startedAt: number;
  durationMs: number;
  name: string;
  attribution: Array<Record<string, unknown>>;
}

export interface BroadcastDiagnosticsState {
  version: string;
  loadedAt: number;
  counters: Record<string, number>;
  timings: {
    buildVariableMappings: { count: number; totalMs: number; maxMs: number };
    refreshImports: { count: number; totalMs: number; maxMs: number };
    refreshDrafts: { count: number; totalMs: number; maxMs: number };
  };
  renderCounts: Record<string, number>;
  selectedImportIdChanges: Array<BroadcastDiagnosticEvent<number | null>>;
  importBusyChanges: Array<BroadcastDiagnosticEvent<boolean>>;
  spans: BroadcastMeasuredCall[];
  longTasks: BroadcastLongTaskRecord[];
  rafTicks: number;
  timeoutTicks: number;
  unhandledRejections: Array<{
    at: number;
    reason: string;
  }>;
}

declare global {
  interface Window {
    __BROADCAST_DIAGNOSTICS__?: BroadcastDiagnosticsState & {
      markRender: (componentName: string) => number;
      recordCounter: (name: string, delta?: number) => number;
      recordSelectedImportIdChange: (value: number | null) => void;
      recordImportBusyChange: (value: boolean) => void;
      measure: <T>(
        label: string,
        fn: () => Promise<T> | T,
        options?: {
          stack?: string;
          meta?: Record<string, unknown>;
          timingBucket?:
            | 'buildVariableMappings'
            | 'refreshImports'
            | 'refreshDrafts';
        },
      ) => Promise<T>;
      getSnapshot: () => BroadcastDiagnosticsState;
    };
  }
}

function now() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function ensureBucket(
  state: BroadcastDiagnosticsState,
  key: keyof BroadcastDiagnosticsState['timings'],
) {
  if (!state.timings[key]) {
    state.timings[key] = { count: 0, totalMs: 0, maxMs: 0 };
  }
  return state.timings[key];
}

export function getBroadcastDiagnostics() {
  if (typeof window === 'undefined') {
    return null;
  }

  if (window.__BROADCAST_DIAGNOSTICS__) {
    return window.__BROADCAST_DIAGNOSTICS__;
  }

  const state: BroadcastDiagnosticsState = {
    version: BROADCAST_DIAGNOSTICS_VERSION,
    loadedAt: Date.now(),
    counters: {},
    timings: {
      buildVariableMappings: { count: 0, totalMs: 0, maxMs: 0 },
      refreshImports: { count: 0, totalMs: 0, maxMs: 0 },
      refreshDrafts: { count: 0, totalMs: 0, maxMs: 0 },
    },
    renderCounts: {},
    selectedImportIdChanges: [],
    importBusyChanges: [],
    spans: [],
    longTasks: [],
    rafTicks: 0,
    timeoutTicks: 0,
    unhandledRejections: [],
  };

  const diagnostics = Object.assign(state, {
    markRender(componentName: string) {
      const nextCount = (state.renderCounts[componentName] ?? 0) + 1;
      state.renderCounts[componentName] = nextCount;
      return nextCount;
    },
    recordCounter(name: string, delta = 1) {
      const nextCount = (state.counters[name] ?? 0) + delta;
      state.counters[name] = nextCount;
      return nextCount;
    },
    recordSelectedImportIdChange(value: number | null) {
      state.selectedImportIdChanges.push({
        at: Date.now(),
        value,
      });
    },
    recordImportBusyChange(value: boolean) {
      state.importBusyChanges.push({
        at: Date.now(),
        value,
      });
    },
    async measure<T>(
      label: string,
      fn: () => Promise<T> | T,
      options?: {
        stack?: string;
        meta?: Record<string, unknown>;
        timingBucket?:
          | 'buildVariableMappings'
          | 'refreshImports'
          | 'refreshDrafts';
      },
    ) {
      const startedAt = now();
      try {
        return await fn();
      } finally {
        const endedAt = now();
        const durationMs = endedAt - startedAt;
        state.spans.push({
          label,
          startedAt,
          endedAt,
          durationMs,
          stack: options?.stack,
          meta: options?.meta,
        });
        if (options?.timingBucket) {
          const bucket = ensureBucket(state, options.timingBucket);
          bucket.count += 1;
          bucket.totalMs += durationMs;
          bucket.maxMs = Math.max(bucket.maxMs, durationMs);
        }
      }
    },
    getSnapshot() {
      return JSON.parse(JSON.stringify(state)) as BroadcastDiagnosticsState;
    },
  });

  window.__BROADCAST_DIAGNOSTICS__ = diagnostics;

  window.addEventListener('unhandledrejection', (event) => {
    diagnostics.unhandledRejections.push({
      at: Date.now(),
      reason:
        event.reason instanceof Error
          ? `${event.reason.name}: ${event.reason.message}`
          : String(event.reason),
    });
  });

  if (
    typeof PerformanceObserver !== 'undefined' &&
    PerformanceObserver.supportedEntryTypes?.includes('longtask')
  ) {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const typedEntry = entry as PerformanceEntry & {
          attribution?: Array<Record<string, unknown>>;
        };
        diagnostics.longTasks.push({
          startedAt: typedEntry.startTime,
          durationMs: typedEntry.duration,
          name: typedEntry.name,
          attribution: typedEntry.attribution ?? [],
        });
      }
    });
    observer.observe({ entryTypes: ['longtask'] });
  }

  const tickRaf = () => {
    diagnostics.rafTicks += 1;
    window.requestAnimationFrame(tickRaf);
  };
  window.requestAnimationFrame(tickRaf);

  const tickTimeout = () => {
    diagnostics.timeoutTicks += 1;
    window.setTimeout(tickTimeout, 1000);
  };
  window.setTimeout(tickTimeout, 1000);

  if (import.meta.env.DEV) {
    console.debug(
      '[broadcast-diagnostics] loaded',
      BROADCAST_DIAGNOSTICS_VERSION,
    );
  }

  return diagnostics;
}

export function markBroadcastRender(componentName: string) {
  const diagnostics = getBroadcastDiagnostics();
  return diagnostics?.markRender(componentName) ?? 0;
}
