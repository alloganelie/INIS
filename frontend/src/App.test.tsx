import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import App from './App';

describe('App Smoke Test', () => {
  it('renders INIS layout without crashing', () => {
    const { container } = render(<App />);
    expect(container).toBeDefined();
    expect(container.querySelector('.inis-app')).not.toBeNull();
    expect(container.textContent).toContain('INIS Intelligence');
  });
});
