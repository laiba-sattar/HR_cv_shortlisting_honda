import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  base: './', // keeps the production build relocatable — dist/ can be opened directly or served from any sub-path
  plugins: [react()],
})
