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

function PhotoCard({
  photo,
  busy,
  onZoom,
  onDelete,
}: {
  photo: TaskPhoto;
  busy: boolean;
  onZoom: () => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="photo-card">
      <AuthImg
        path={photo.url}
        alt={photo.caption || "Task photo"}
        className="photo-thumb"
        onClick={onZoom}
      />
      {confirming ? (
        <div className="photo-confirm">
          <span>Delete photo?</span>
          <button
            className="danger"
            disabled={busy}
            onClick={() => {
              setConfirming(false);
              onDelete();
            }}
          >
            Yes
          </button>
          <button className="ghost" disabled={busy} onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <button className="ghost photo-del" disabled={busy} onClick={() => setConfirming(true)}>
          Delete
        </button>
      )}
    </div>
  );
}

export function PhotoGallery({
  photos,
  busy = false,
  onDelete,
}: {
  photos: TaskPhoto[];
  busy?: boolean;
  onDelete?: (photoId: string) => void;
}) {
  const [zoom, setZoom] = useState<TaskPhoto | null>(null);
  if (!photos.length) return null;

  return (
    <div style={{ marginTop: 16 }}>
      <label>Photos ({photos.length})</label>
      <div className="photo-strip">
        {photos.map((p) => (
          <PhotoCard
            key={p.id}
            photo={p}
            busy={busy}
            onZoom={() => setZoom(p)}
            onDelete={() => onDelete?.(p.id)}
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
