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

  type BroadcastDiagnosticsEnvLike = {
    DEV?: boolean;
  };

  type BroadcastDiagnosticsWindowLike = Window & {
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
  };

  type BroadcastPerformanceEntryLike = PerformanceEntry & {
    attribution?: Array<Record<string, unknown>>;
  };

  type BroadcastPerformanceObserverLike = {
    observe: (options: { entryTypes: string[] }) => void;
  };

  type BroadcastPerformanceObserverCtor = {
    new (callback: {
      (list: { getEntries(): BroadcastPerformanceEntryLike[] }): void;
    }): BroadcastPerformanceObserverLike;
    supportedEntryTypes?: readonly string[];
  };

  interface BroadcastDiagnosticsRuntime {
    env?: BroadcastDiagnosticsEnvLike;
    window?: BroadcastDiagnosticsWindowLike;
    PerformanceObserver?: BroadcastPerformanceObserverCtor;
    consoleDebug?: (...args: unknown[]) => void;
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

function pushLimited<T>(items: T[], value: T, limit = 200) {
  items.push(value);
  if (items.length > limit) {
    items.splice(0, items.length - limit);
  }
}

export function getBroadcastDiagnostics() {
  return getBroadcastDiagnosticsWithRuntime({
    env: import.meta.env,
    window:
      typeof window === 'undefined'
        ? undefined
        : (window as BroadcastDiagnosticsWindowLike),
    PerformanceObserver:
      typeof PerformanceObserver === 'undefined'
        ? undefined
        : (PerformanceObserver as unknown as BroadcastPerformanceObserverCtor),
    consoleDebug: (...args) => console.debug(...args),
  });
}

export function getBroadcastDiagnosticsWithRuntime(
  runtime: BroadcastDiagnosticsRuntime,
) {
  const runtimeWindow = runtime.window;
  if (!runtime.env?.DEV || !runtimeWindow) {
    return null;
  }

  if (runtimeWindow.__BROADCAST_DIAGNOSTICS__) {
    return runtimeWindow.__BROADCAST_DIAGNOSTICS__;
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
      pushLimited(state.selectedImportIdChanges, {
        at: Date.now(),
        value,
      });
    },
    recordImportBusyChange(value: boolean) {
      pushLimited(state.importBusyChanges, {
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
        pushLimited(state.spans, {
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

  runtimeWindow.__BROADCAST_DIAGNOSTICS__ = diagnostics;

  runtimeWindow.addEventListener('unhandledrejection', (event) => {
    pushLimited(diagnostics.unhandledRejections, {
      at: Date.now(),
      reason:
        event.reason instanceof Error
          ? `${event.reason.name}: ${event.reason.message}`
          : String(event.reason),
    });
  });

  if (
    runtime.PerformanceObserver &&
    runtime.PerformanceObserver.supportedEntryTypes?.includes('longtask')
  ) {
    const observer = new runtime.PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const typedEntry = entry as BroadcastPerformanceEntryLike;
        pushLimited(diagnostics.longTasks, {
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
    runtimeWindow.requestAnimationFrame(tickRaf);
  };
  runtimeWindow.requestAnimationFrame(tickRaf);

  const tickTimeout = () => {
    diagnostics.timeoutTicks += 1;
    runtimeWindow.setTimeout(tickTimeout, 1000);
  };
  runtimeWindow.setTimeout(tickTimeout, 1000);

  if (runtime.env?.DEV) {
    runtime.consoleDebug?.(
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
