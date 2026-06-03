const AVATAR_MAX_EDGE_PX = 512;
const AVATAR_JPEG_QUALITY = 0.85;
const AVATAR_SERVER_LIMIT_BYTES = 2 * 1024 * 1024;

export async function prepareAvatarUpload(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) {
    return file;
  }
  if (typeof document === "undefined" || typeof URL.createObjectURL !== "function") {
    return file;
  }

  try {
    const image = await loadImage(file);
    const width = image.naturalWidth;
    const height = image.naturalHeight;
    if (width <= 0 || height <= 0) {
      return file;
    }

    const scale = Math.min(1, AVATAR_MAX_EDGE_PX / Math.max(width, height));
    const targetWidth = Math.max(1, Math.round(width * scale));
    const targetHeight = Math.max(1, Math.round(height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      return file;
    }
    context.drawImage(image, 0, 0, targetWidth, targetHeight);

    const blob = await canvasToBlob(canvas, "image/jpeg", AVATAR_JPEG_QUALITY);
    if (!blob) {
      return file;
    }
    if (blob.size >= file.size && file.size <= AVATAR_SERVER_LIMIT_BYTES) {
      return file;
    }
    return new File([blob], avatarFileName(file.name), {
      type: "image/jpeg",
      lastModified: file.lastModified || Date.now(),
    });
  } catch {
    return file;
  }
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    const finish = () => URL.revokeObjectURL(url);
    image.onload = () => {
      finish();
      resolve(image);
    };
    image.onerror = () => {
      finish();
      reject(new Error("Unable to load avatar image"));
    };
    image.decoding = "async";
    image.src = url;
  });
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

function avatarFileName(name: string): string {
  const baseName = name.replace(/\.[^.]*$/, "").trim() || "avatar";
  return `${baseName}.jpg`;
}
