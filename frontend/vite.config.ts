import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// El frontend habla con la API SPC por su base URL (VITE_API_BASE_URL,
// por defecto http://localhost:8010). En dev se levanta la API con
// SPC_CORS_ORIGINS=http://localhost:5173 (ya soportado por el backend).
//
// `base` controla el path raíz del bundle. En dev/local es '/'; al desplegar
// en GitHub Pages (project site) hay que servir bajo '/<repo>/', así que el
// workflow inyecta VITE_BASE=/sistema_predicion_comercializacion/.
// https://vite.dev/config/
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
})
