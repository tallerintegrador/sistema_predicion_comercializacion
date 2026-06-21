import { describe, it, expect } from 'vitest'
import {
  CURRENCY_LABELS,
  REGION_LABELS,
  SECTOR_LABELS,
  SIZE_LABELS,
  labelFor,
  orderCodes,
} from './onboardingLabels'

// Códigos que sirve el backend hoy (src/spc/api/schemas/auth.py). Si el backend añade uno,
// estas listas recuerdan que falta su etiqueta en español (la prueba fallaría).
const BACKEND = {
  sectors: ['retail', 'wholesale', 'supermarket', 'pharmacy', 'hardware', 'food_service', 'other'],
  sizes: ['micro', 'small', 'medium'],
  regions: ['north_america', 'central_america', 'south_america', 'europe', 'africa', 'asia', 'oceania'],
  currencies: ['USD', 'EUR', 'PEN', 'COP', 'MXN', 'CLP', 'ARS', 'BRL'],
}

describe('etiquetas del onboarding (sin códigos en inglés)', () => {
  it.each([
    ['rubro', SECTOR_LABELS, BACKEND.sectors],
    ['tamaño', SIZE_LABELS, BACKEND.sizes],
    ['región', REGION_LABELS, BACKEND.regions],
    ['moneda', CURRENCY_LABELS, BACKEND.currencies],
  ] as const)('cada código de %s se muestra con etiqueta en español', (_n, map, codes) => {
    for (const code of codes) {
      const label = labelFor(map, code)
      expect(label).toBeTruthy()
      expect(label).not.toBe(code) // nunca exponemos el código crudo
    }
  })
})

describe('orderCodes', () => {
  it('pone los preferidos primero', () => {
    expect(orderCodes(['USD', 'EUR', 'PEN'], ['PEN', 'USD'])).toEqual(['PEN', 'USD', 'EUR'])
  })
  it('ignora los preferidos que no están presentes', () => {
    expect(orderCodes(['USD', 'EUR'], ['PEN'])).toEqual(['USD', 'EUR'])
  })
})
