import "@testing-library/jest-dom/vitest"

// Node 25 ships a built-in (but incomplete) `localStorage`/`sessionStorage`
// global that prevents jsdom's full Storage implementation from being used.
// vitest's populateGlobal skips keys that already exist on the global and are
// not in its hard-coded KEYS list — so `localStorage` stays as Node's broken
// stub.  We fix it here by pulling the real Storage from jsdom's own window.
const jsdomWindow = (globalThis as unknown as { jsdom?: { window: Window } }).jsdom?.window
if (jsdomWindow) {
  Object.defineProperty(globalThis, "localStorage", {
    get: () => jsdomWindow.localStorage,
    configurable: true,
  })
  Object.defineProperty(globalThis, "sessionStorage", {
    get: () => jsdomWindow.sessionStorage,
    configurable: true,
  })
}
