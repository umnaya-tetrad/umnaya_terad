import { afterEach, expect, test, vi } from 'vitest'
import { prepareUpload } from './compress'

afterEach(() => vi.unstubAllGlobals())
const photo = (bytes = 900_000, type = 'image/jpeg') => new Blob([new Uint8Array(bytes)], { type })

function canvas(width: number, height: number, output: Blob | null) {
  const bitmap = { width, height, close: vi.fn() }
  const drawImage = vi.fn()
  const context = { fillStyle: '', fillRect: vi.fn(), drawImage }
  const value = { width: 0, height: 0, getContext: () => context,
    toBlob: (callback: (blob: Blob | null) => void) => callback(output) }
  const decode = vi.fn().mockResolvedValue(bitmap)
  vi.stubGlobal('createImageBitmap', decode)
  vi.stubGlobal('document', { createElement: () => value })
  return { value, bitmap, decode, drawImage }
}

test('small images and HEIC retain original bytes without requiring a decoder', async () => {
  const small = photo(400_000)
  const heic = photo(900_000, 'image/heic')
  expect(await prepareUpload(small)).toBe(small)
  expect(await prepareUpload(heic)).toBe(heic)
})

test('large image keeps orientation, aspect ratio and closes decoded memory', async () => {
  const original = photo()
  const output = photo(300_000)
  const mock = canvas(6000, 4000, output)
  expect(await prepareUpload(original)).toBe(output)
  expect(mock.decode).toHaveBeenCalledWith(original, { imageOrientation: 'from-image' })
  expect(mock.value.width).toBe(3200)
  expect(mock.value.height).toBe(2133)
  expect(mock.bitmap.close).toHaveBeenCalledOnce()
})

test('does not upscale a smaller-resolution photo', async () => {
  const original = photo()
  const mock = canvas(1200, 1600, photo(300_000))
  await prepareUpload(original)
  expect([mock.value.width, mock.value.height]).toEqual([1200, 1600])
})

test('retains original if reencoding is larger or canvas fails', async () => {
  const original = photo()
  canvas(6000, 4000, photo(950_000))
  expect(await prepareUpload(original)).toBe(original)
  canvas(6000, 4000, null)
  expect(await prepareUpload(original)).toBe(original)
  vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('unsupported decoder')))
  expect(await prepareUpload(original)).toBe(original)
})
