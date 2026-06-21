/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Configuración de pruebas (smoke) del frontend. Usa jsdom para poder renderizar
// componentes. No procesa Tailwind: las pruebas comprueban contenido/idioma, no estilos.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
})
