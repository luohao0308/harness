import { afterEach, describe, expect, it, vi } from "vitest";

import { prepareAvatarUpload } from "../avatarUpload";

const originalImage = globalThis.Image;
const originalCreateObjectUrl = URL.createObjectURL;
const originalRevokeObjectUrl = URL.revokeObjectURL;

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.Image = originalImage;
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: originalCreateObjectUrl,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: originalRevokeObjectUrl,
  });
});

describe("prepareAvatarUpload", () => {
  it("returns non-image files unchanged", async () => {
    const file = new File(["not-avatar"], "note.txt", { type: "text/plain" });

    await expect(prepareAvatarUpload(file)).resolves.toBe(file);
  });

  it("resizes image files to a JPEG upload payload", async () => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(() => "blob:avatar"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
    const drawImage = vi.fn();
    const jpegBlob = new Blob(["compressed-avatar"], { type: "image/jpeg" });
    const createElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName !== "canvas") {
        return createElement(tagName);
      }
      return {
        width: 0,
        height: 0,
        getContext: () => ({ drawImage }),
        toBlob: (callback: BlobCallback) => callback(jpegBlob),
      } as unknown as HTMLCanvasElement;
    });

    globalThis.Image = class {
      naturalWidth = 1600;
      naturalHeight = 800;
      decoding: "async" | "sync" | "auto" = "auto";
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;

      set src(_value: string) {
        this.onload?.();
      }
    } as unknown as typeof Image;

    const file = new File(["large-avatar".repeat(20)], "avatar.png", {
      type: "image/png",
      lastModified: 123,
    });
    const prepared = await prepareAvatarUpload(file);

    expect(prepared).not.toBe(file);
    expect(prepared.name).toBe("avatar.jpg");
    expect(prepared.type).toBe("image/jpeg");
    expect(prepared.lastModified).toBe(123);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 512, 256);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:avatar");
  });
});
