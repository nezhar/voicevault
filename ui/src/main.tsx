import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.tsx';
import { UploadPage } from './components/UploadPage';
import { AuthProvider } from './context/AuthContext';
import { parsePath } from './hooks/useRoute';
import './index.css';

// Upload links authorize themselves, so their page skips the login flow.
const isUploadPage = parsePath(window.location.pathname).kind === 'upload';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isUploadPage ? (
      <UploadPage />
    ) : (
      <AuthProvider>
        <App />
      </AuthProvider>
    )}
  </React.StrictMode>,
);
