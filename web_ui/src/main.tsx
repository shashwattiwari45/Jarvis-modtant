import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import { OwnerAuthGate } from './components/OwnerAuthGate';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <OwnerAuthGate>
      <App />
    </OwnerAuthGate>
  </StrictMode>,
);
