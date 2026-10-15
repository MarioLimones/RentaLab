import '@testing-library/jest-dom/vitest';

// jsdom no tiene un área visual; el desplazamiento al navegar se comprueba en un navegador real.
window.scrollTo = () => {};
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
