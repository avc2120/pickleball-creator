"use client";

import { useState } from "react";

type Sport = "pickleball" | "golf";

const config = {
  pickleball: {
    badge: "🏓 AI-powered pickleball reels",
    title: "Turn pickleball rallies into vertical highlights.",
    description:
      "Upload a short horizontal clip. Pickleball Creator tracks the rally, reframes the action, and exports an Instagram-ready reel.",
    features: ["YOLO player tracking", "Smooth camera path", "9:16 reel export"],
    uploadText: "Click to upload a pickleball video",
    buttonText: "Create Reel",
    processingText: "Directing your rally...",
    progressText: "Detecting players, calculating camera path, exporting video...",
    downloadName: "pickleball-reel.mp4",
  },
  golf: {
    badge: "⛳ Golf swing stitcher",
    title: "Turn range sessions into clean swing montages.",
    description:
      "Upload a golf practice video. We detect your swings, cut out the downtime, and stitch everything into a clean highlight.",
    features: ["Swing detection", "Downtime removal", "Montage export"],
    uploadText: "Click to upload a golf video",
    buttonText: "Create Swing Montage",
    processingText: "Stitching your swings...",
    progressText: "Detecting swings, trimming downtime, stitching clips...",
    downloadName: "golf-swing-montage.mp4",
  },
} satisfies Record<Sport, {
  badge: string;
  title: string;
  description: string;
  features: string[];
  uploadText: string;
  buttonText: string;
  processingText: string;
  progressText: string;
  downloadName: string;
}>;

export default function Home() {
  const [sport, setSport] = useState<Sport>("pickleball");
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  const ui = config[sport];

  async function processVideo() {
    if (!file) return;

    setIsProcessing(true);
    setError("");
    setDownloadUrl(null);

    const formData = new FormData();
    formData.append("video", file);
    formData.append("sport", sport);

    try {
      const res = await fetch("/api/process-video", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error("Failed to process video");

      const blob = await res.blob();
      setDownloadUrl(URL.createObjectURL(blob));
    } catch {
      setError("Something went wrong processing the video.");
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-lime-100 px-6 py-10 text-slate-950">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl flex-col justify-center gap-10 lg:grid lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
        <section className="space-y-8">
          <div className="inline-flex rounded-full border border-emerald-200 bg-white/70 px-4 py-2 text-sm font-medium text-emerald-700 shadow-sm backdrop-blur">
            {ui.badge}
          </div>

          <div className="inline-flex rounded-2xl bg-slate-100 p-1 shadow-sm">
            <button
              type="button"
              onClick={() => {
                setSport("pickleball");
                setDownloadUrl(null);
                setError("");
              }}
              className={`rounded-xl px-4 py-2 text-sm transition ${
                sport === "pickleball"
                  ? "bg-white font-semibold text-slate-950 shadow"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              🏓 Pickleball
            </button>

            <button
              type="button"
              onClick={() => {
                setSport("golf");
                setDownloadUrl(null);
                setError("");
              }}
              className={`rounded-xl px-4 py-2 text-sm transition ${
                sport === "golf"
                  ? "bg-white font-semibold text-slate-950 shadow"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              ⛳ Golf
            </button>
          </div>

          <div className="space-y-5">
            <h1 className="text-5xl font-black tracking-tight text-slate-950 sm:text-6xl">
              {ui.title}
            </h1>

            <p className="max-w-xl text-lg leading-8 text-slate-600">
              {ui.description}
            </p>
          </div>

          <div className="grid max-w-xl gap-3 sm:grid-cols-3">
            {ui.features.map((item) => (
              <div
                key={item}
                className="rounded-2xl border border-white/80 bg-white/70 p-4 text-sm font-semibold text-slate-700 shadow-sm backdrop-blur"
              >
                {item}
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[2rem] border border-white/80 bg-white/80 p-6 shadow-2xl shadow-emerald-900/10 backdrop-blur">
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold">
                {sport === "golf" ? "Create your montage" : "Create your reel"}
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                Best with clips under 1 minute for now. Tiny empire, sensible limits.
              </p>
            </div>

            <label className="flex cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed border-emerald-200 bg-emerald-50/60 px-6 py-10 text-center transition hover:border-emerald-400 hover:bg-emerald-50">
              <input
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setDownloadUrl(null);
                  setError("");
                }}
              />

              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-600 text-2xl text-white shadow-lg shadow-emerald-600/25">
                ⬆
              </div>

              <p className="font-semibold text-slate-800">
                {file ? file.name : ui.uploadText}
              </p>

              <p className="mt-2 text-sm text-slate-500">
                MP4, MOV, or any short video clip
              </p>
            </label>

            {file && (
              <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
                <div className="font-medium text-slate-900">Selected file</div>
                <div className="mt-1 truncate">{file.name}</div>
                <div className="mt-1">
                  {(file.size / 1024 / 1024).toFixed(1)} MB
                </div>
              </div>
            )}

            <button
              onClick={processVideo}
              disabled={!file || isProcessing}
              className="flex w-full items-center justify-center rounded-2xl bg-slate-950 px-5 py-4 text-sm font-bold text-white shadow-lg shadow-slate-950/20 transition hover:-translate-y-0.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
            >
              {isProcessing ? ui.processingText : ui.buttonText}
            </button>

            {isProcessing && (
              <div className="space-y-2">
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full w-1/2 animate-pulse rounded-full bg-emerald-500" />
                </div>
                <p className="text-center text-sm text-slate-500">
                  {ui.progressText}
                </p>
              </div>
            )}

            {error && (
              <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700">
                {error}
              </div>
            )}

            {downloadUrl && (
              <div className="space-y-4 rounded-3xl border border-emerald-100 bg-emerald-50/60 p-4">
                <video
                  src={downloadUrl}
                  controls
                  className="mx-auto max-h-[520px] rounded-2xl bg-black shadow-xl"
                />

                <a
                  href={downloadUrl}
                  download={ui.downloadName}
                  className="block rounded-2xl bg-emerald-600 px-5 py-4 text-center text-sm font-bold text-white shadow-lg shadow-emerald-600/20 transition hover:-translate-y-0.5 hover:bg-emerald-700"
                >
                  Download
                </a>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}