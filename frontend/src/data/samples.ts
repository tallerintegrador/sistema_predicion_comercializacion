/**
 * Datos de ejemplo del frontend. Son los mismos `examples/api/*.json` del repo
 * (≈130 filas de history, 2 tiendas, familia BEVERAGES de Corporación Favorita),
 * copiados aquí para reutilizarlos sin fabricar series nuevas.
 */
import type { InventoryRequest, PurchasesRequest, SalesRequest } from '../api/types'

import salesJson from './samples/sales.json'
import purchasesJson from './samples/purchases.json'
import inventoryJson from './samples/inventory.json'

export const sampleSales = salesJson as unknown as SalesRequest
export const samplePurchases = purchasesJson as unknown as PurchasesRequest
export const sampleInventory = inventoryJson as unknown as InventoryRequest
