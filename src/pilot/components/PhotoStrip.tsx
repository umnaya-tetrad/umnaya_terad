import type { PilotApi } from '../api/client'
import type { Photo } from '../api/contract'
import { copy } from '../copy'
import { usePhoto } from '../photos'

export function PhotoThumbnail({ api, photo, label, open }: { api: PilotApi; photo: Photo; label: string; open: () => void }) {
  const loaded = usePhoto(api, photo.id)
  return <button className="thumbnail" onClick={open} aria-label={`${label}. ${copy('result.enlarge')}`}>
    {loaded?.url && <img src={loaded.url} alt="" />}
    <span>{label}</span>
  </button>
}
