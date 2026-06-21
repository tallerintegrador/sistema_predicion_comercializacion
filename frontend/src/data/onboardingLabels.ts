/**
 * Etiquetas de **visualización** en español para el onboarding del negocio.
 *
 * El backend valida `sector/size/region/currency` contra códigos fijos (en inglés), así que
 * la UI **sigue enviando esos códigos**; aquí solo se traduce su PRESENTACIÓN, sin alterar el
 * valor que se envía/almacena (ADR-0019, restricción de lenguaje sin tecnicismos). Si el
 * backend añade un código nuevo sin etiqueta, `labelFor` muestra el código como último recurso
 * y la prueba de cobertura recuerda añadir su traducción.
 *
 * Algunas opciones deseables (más rubros, "Gran empresa", regiones del Perú, etc.) requieren
 * códigos que el backend aún no expone: ver docs/alineacion_frontend_backend.md §8.
 */

export const SECTOR_LABELS: Record<string, string> = {
  retail: 'Comercio minorista',
  wholesale: 'Comercio mayorista',
  supermarket: 'Supermercado / abarrotes',
  pharmacy: 'Farmacia / salud',
  hardware: 'Ferretería / construcción',
  food_service: 'Restaurante / comida',
  other: 'Otro',
}

export const SIZE_LABELS: Record<string, string> = {
  micro: 'Microempresa',
  small: 'Pequeña empresa',
  medium: 'Mediana empresa',
}

export const REGION_LABELS: Record<string, string> = {
  north_america: 'América del Norte',
  central_america: 'Centroamérica',
  south_america: 'América del Sur',
  europe: 'Europa',
  africa: 'África',
  asia: 'Asia',
  oceania: 'Oceanía',
}

export const CURRENCY_LABELS: Record<string, string> = {
  PEN: 'Sol peruano (S/)',
  USD: 'Dólar estadounidense (US$)',
  EUR: 'Euro (€)',
  COP: 'Peso colombiano (COL$)',
  MXN: 'Peso mexicano (MX$)',
  CLP: 'Peso chileno (CLP$)',
  ARS: 'Peso argentino (AR$)',
  BRL: 'Real brasileño (R$)',
}

/** Orden de presentación preferido por campo (los demás van después, en el orden recibido). */
export const PREFERRED_ORDER: Record<string, string[]> = {
  currency: ['PEN', 'USD', 'EUR'],
}

/** Etiqueta en español de un código; si no hay traducción, devuelve el propio código. */
export function labelFor(map: Record<string, string>, code: string): string {
  return map[code] ?? code
}

/** Reordena los códigos poniendo primero los preferidos (si están presentes). */
export function orderCodes(codes: string[], preferred: string[] = []): string[] {
  const pref = preferred.filter((c) => codes.includes(c))
  const rest = codes.filter((c) => !pref.includes(c))
  return [...pref, ...rest]
}
