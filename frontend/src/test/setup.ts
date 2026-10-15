import '@testing-library/jest-dom/vitest';

// jsdom has no visual viewport; route scrolling is verified in the real browser.
window.scrollTo = () => {};
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
