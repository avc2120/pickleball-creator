/**
 * API route that processes an uploaded video by detecting player motion,
 * rendering a smooth vertical crop sequence, and recombining video with audio.
 */
import { NextRequest } from "next/server";
import { writeFile, readFile, unlink, rm } from "fs/promises";
import { spawn, execFile } from "child_process";
import { promisify } from "util";
import path from "path";
import os from "os";
import crypto from "crypto";

export const runtime = "nodejs";
const execFileAsync = promisify(execFile);
const pythonExecutable = path.join(process.cwd(), "yolo-env", "bin", "python");
const detectorScript = path.join(process.cwd(), "scripts", "find_ball_crop.py");
const renderScript = path.join(process.cwd(), "scripts", "render_smooth_reel.py");
const ffmpegExecutable = "ffmpeg";

// MotionPoint represents a camera target sample produced by the Python detector.
type MotionPoint = {
  t: number;
  centerX: number;
  centerY?: number;
  playerSpanWidth?: number;
  playerSpanHeight?: number;
};

// Spawn a child process and collect stderr for error reporting.
function spawnCommand(command: string, args: string[]) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn(command, args);
    let stderr = "";

    child.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(stderr));
    });
  });
}

// Convert a runtime value to a number only when safe.
function safeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : null;
}

function safeParseNumber(value: unknown): number {
  return typeof value === "number"
    ? value
    : parseFloat(String(value)) || 0;
}

// Parse JSON output from the detector script and normalize fields.
function parseDetectorOutput(stdout: string): MotionPoint[] {
  const rawOutput = stdout.trim();
  const firstBrace = rawOutput.indexOf("{");
  const jsonText = firstBrace !== -1 ? rawOutput.slice(firstBrace) : rawOutput;
  const result = JSON.parse(jsonText);
  const points = Array.isArray(result.points) ? result.points : [];

  return points
    .map((point: any) => ({
      t: safeParseNumber(point.t),
      centerX:
        safeNumber(point.centerX) ?? safeNumber(point.ballX) ?? null,
      centerY: safeNumber(point.centerY),
      playerSpanWidth: safeNumber(point.playerSpanWidth),
      playerSpanHeight: safeNumber(point.playerSpanHeight),
    }))
    .filter((point) => point.centerX !== null) as MotionPoint[];
}

// Run the Python detector and return normalized motion points.
async function findMotionPoints(inputPath: string): Promise<MotionPoint[]> {
  try {
    const { stdout, stderr } = await execFileAsync(pythonExecutable, [
      detectorScript,
      inputPath,
    ], {
      maxBuffer: 20 * 1024 * 1024,
    });

    if (stderr) {
      console.error("Python detector stderr:", stderr);
    }

    return parseDetectorOutput(stdout);
  } catch (error) {
    console.error("Detection failed", error);
    return [];
  }
}

// Generate a unique temporary path for intermediate files.
function createTempPath(suffix: string) {
  return path.join(os.tmpdir(), `${crypto.randomUUID()}-${suffix}`);
}

// Run the Python rendering script to generate cropped frames.
async function renderFrames(
  inputPath: string,
  pointsPath: string,
  framesDir: string
) {
  await spawnCommand(pythonExecutable, [
    renderScript,
    inputPath,
    pointsPath,
    framesDir,
  ]);
}

// Combine the generated frames with the original audio track.
async function encodeVideo(
  framesDir: string,
  inputPath: string,
  outputPath: string
) {
  await spawnCommand(ffmpegExecutable, [
    "-framerate",
    "30",
    "-i",
    path.join(framesDir, "frame_%06d.jpg"),
    "-i",
    inputPath,
    "-map",
    "0:v:0",
    "-map",
    "1:a?",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
    "-shortest",
    "-y",
    outputPath,
  ]);
}

// Remove temporary files created during processing.
async function cleanupPaths(paths: string[]) {
  await Promise.all(
    paths.map(async (target) => {
      try {
        await unlink(target);
      } catch {
        // ignore missing files
      }
    })
  );
}

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const file = formData.get("video");

  if (!(file instanceof File)) {
    return Response.json({ error: "No video uploaded" }, { status: 400 });
  }

  if (file.size > 100 * 1024 * 1024) {
    return Response.json({ error: "File too large. Max 100MB." }, { status: 400 });
  }

  // Prepare temp paths for the uploaded source, final output, detector points, and frame directory.

  const inputPath = createTempPath("input.mp4");
  const outputPath = createTempPath("output.mp4");
  const pointsPath = createTempPath("points.json");
  const framesDir = createTempPath("frames");

  try {
    const bytes = await file.arrayBuffer();
    await writeFile(inputPath, Buffer.from(bytes));

    // Detect motion and player targets with the helper Python script.
    const points = await findMotionPoints(inputPath);
    console.log("Detected motion points:", points.slice(0, 30));

    // Render the cropped frame sequence and then encode it back to MP4.
    await writeFile(pointsPath, JSON.stringify({ points }));
    await renderFrames(inputPath, pointsPath, framesDir);
    await encodeVideo(framesDir, inputPath, outputPath);

    const outputBuffer = await readFile(outputPath);
    return new Response(outputBuffer, {
      headers: {
        "Content-Type": "video/mp4",
        "Content-Disposition": `attachment; filename="pickleball-reel.mp4"`,
      },
    });
  } catch (error) {
    console.error(error);
    return Response.json({ error: "Video processing failed" }, { status: 500 });
  } finally {
    await cleanupPaths([inputPath, outputPath, pointsPath]);

    try {
      await rm(framesDir, { recursive: true, force: true });
    } catch {
      // ignore cleanup failures
    }
  }
}

