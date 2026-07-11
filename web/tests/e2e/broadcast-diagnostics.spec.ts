import { expect, test } from '@playwright/test';

test.describe('broadcast diagnostics runtime', () => {
  test('returns null without side effects when DEV is false', async ({
    page,
  }) => {
    await page.goto('/');

    const result = await page.evaluate(async () => {
      let addEventListenerCalls = 0;
      let requestAnimationFrameCalls = 0;
      let setTimeoutCalls = 0;
      let performanceObserverConstructed = 0;
      let consoleDebugCalls = 0;

      const diagnosticsModulePath = [
        '',
        'src',
        'app',
        'home',
        'broadcast',
        'diagnostics.ts',
      ].join('/');
      const diagnosticsModule = await import(
        /* @vite-ignore */ diagnosticsModulePath
      );
      const { getBroadcastDiagnosticsWithRuntime } = diagnosticsModule as {
        getBroadcastDiagnosticsWithRuntime: (runtime: {
          env?: { DEV?: boolean };
          window?: {
            __BROADCAST_DIAGNOSTICS__?: unknown;
            addEventListener: () => void;
            requestAnimationFrame: () => number;
            setTimeout: () => number;
          };
          PerformanceObserver?: new () => { observe(): void };
          consoleDebug?: () => void;
        }) => unknown;
      };

      const fakeWindow = {
        addEventListener: () => {
          addEventListenerCalls += 1;
        },
        requestAnimationFrame: () => {
          requestAnimationFrameCalls += 1;
          return 1;
        },
        setTimeout: () => {
          setTimeoutCalls += 1;
          return 1;
        },
      };

      class FakePerformanceObserver {
        static supportedEntryTypes = ['longtask'];

        constructor() {
          performanceObserverConstructed += 1;
        }

        observe() {
          throw new Error('observe should not be called in non-DEV mode');
        }
      }

      const diagnostics = getBroadcastDiagnosticsWithRuntime({
        env: { DEV: false },
        window: fakeWindow,
        PerformanceObserver: FakePerformanceObserver,
        consoleDebug: () => {
          consoleDebugCalls += 1;
        },
      });

      return {
        diagnostics,
        hasDiagnosticsGlobal:
          '__BROADCAST_DIAGNOSTICS__' in fakeWindow &&
          fakeWindow.__BROADCAST_DIAGNOSTICS__ !== undefined,
        addEventListenerCalls,
        requestAnimationFrameCalls,
        setTimeoutCalls,
        performanceObserverConstructed,
        consoleDebugCalls,
      };
    });

    expect(result.diagnostics).toBeNull();
    expect(result.hasDiagnosticsGlobal).toBe(false);
    expect(result.addEventListenerCalls).toBe(0);
    expect(result.requestAnimationFrameCalls).toBe(0);
    expect(result.setTimeoutCalls).toBe(0);
    expect(result.performanceObserverConstructed).toBe(0);
    expect(result.consoleDebugCalls).toBe(0);
  });
});
