"use client";

import { useState } from "react";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function processVideo() {
    if (!file) return;

    setIsProcessing(true);
    setError("");
    setDownloadUrl(null);

    const formData = new FormData();
    formData.append("video", file);

    try {
      const res = await fetch("/api/process-video", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Failed to process video");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setDownloadUrl(url);
    } catch {
      setError("Something went wrong processing the video.");
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <div className="w-full max-w-xl space-y-6">
        <h1 className="text-3xl font-bold">Pickleball Creator</h1>

        <p className="text-gray-600">
          Upload a short pickleball video and convert it into a vertical reel.
        </p>

        <input
          type="file"
          accept="video/*"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full"
        />

        {file && (
          <p className="text-sm text-gray-600">
            Selected: {file.name}
          </p>
        )}

        <button
          onClick={processVideo}
          disabled={!file || isProcessing}
          className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
        >
          {isProcessing ? "Processing..." : "Create Reel"}
        </button>

        {error && <p className="text-red-600">{error}</p>}

        {downloadUrl && (
          <div className="space-y-4">
            <video src={downloadUrl} controls className="max-h-[500px] rounded" />

            <a
              href={downloadUrl}
              download="pickleball-reel.mp4"
              className="inline-block rounded bg-green-700 px-4 py-2 text-white"
            >
              Download Reel
            </a>
          </div>
        )}
      </div>
    </main>
  );
}
