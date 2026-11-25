/** Keep small originals; preserve orientation and mathematical detail, no upscale. */
export async function prepareUpload(blob: Blob): Promise<Blob> {
  if (blob.size < 650_000 || !/^image\/(jpeg|png|webp)$/i.test(blob.type)) return blob
  let bitmap: ImageBitmap | undefined
  try {
    bitmap = await createImageBitmap(blob, { imageOrientation: 'from-image' })
    // 3200px leaves fine exponents on dense A4 sheets readable. Never enlarge.
    const scale = Math.min(1, 3200 / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) return blob
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const compressed = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', .9))
    // Do not reencode unless there is a material byte saving.
    return compressed && compressed.size < blob.size * .85 ? compressed : blob
  } catch { return blob }
  finally { bitmap?.close() }
}
