import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// El frontend habla con la API SPC por su base URL (VITE_API_BASE_URL,
// por defecto http://localhost:8010). En dev se levanta la API con
// SPC_CORS_ORIGINS=http://localhost:5173 (ya soportado por el backend).
// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
})
