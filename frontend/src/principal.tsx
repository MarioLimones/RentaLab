import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import Aplicacion from './Aplicacion';
import './estilos.css';

const raiz = document.getElementById('root');
if (!raiz) throw new Error('No se encontró el punto de montaje de RentaLab.');

createRoot(raiz).render(
  <StrictMode>
    <BrowserRouter>
      <Aplicacion />
    </BrowserRouter>
  </StrictMode>,
);
