import { useEffect, useState } from "react";
import { fetchObjectUrl, type TaskPhoto } from "./api";

/** Loads an authenticated image (bearer token) as an object URL. */
function AuthImg({
  path,
  alt,
  className,
  onClick,
}: {
  path: string;
  alt: string;
  className?: string;
  onClick?: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let url: string | null = null;
    let live = true;
    setFailed(false);
    setSrc(null);
    fetchObjectUrl(path)
      .then((u) => {
        if (!live) {
          URL.revokeObjectURL(u);
          return;
        }
        url = u;
        setSrc(u);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);

  if (failed) return <span className="photo-fail">image unavailable</span>;
  if (!src) return <span className="photo-loading" />;
  return <img src={src} alt={alt} className={className} onClick={onClick} />;
}

export function PhotoGallery({ photos }: { photos: TaskPhoto[] }) {
  const [zoom, setZoom] = useState<TaskPhoto | null>(null);
  if (!photos.length) return null;

  return (
    <div style={{ marginTop: 16 }}>
      <label>Photos ({photos.length})</label>
      <div className="photo-strip">
        {photos.map((p) => (
          <AuthImg
            key={p.id}
            path={p.url}
            alt={p.caption || "Task photo"}
            className="photo-thumb"
            onClick={() => setZoom(p)}
          />
        ))}
      </div>
      {zoom && (
        <div className="photo-lightbox" onClick={() => setZoom(null)}>
          <AuthImg path={zoom.url} alt={zoom.caption || "Task photo"} className="photo-full" />
          {zoom.caption && <div className="photo-caption">{zoom.caption}</div>}
        </div>
      )}
    </div>
  );
}
