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

type MotionPoint = {
  t: number;
  centerX: number;
  centerY?: number;
  playerSpanWidth?: number;
  playerSpanHeight?: number;
};

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

function createTempPath(suffix: string) {
  return path.join(os.tmpdir(), `${crypto.randomUUID()}-${suffix}`);
}

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

  const inputPath = createTempPath("input.mp4");
  const outputPath = createTempPath("output.mp4");
  const pointsPath = createTempPath("points.json");
  const framesDir = createTempPath("frames");

  try {
    const bytes = await file.arrayBuffer();
    await writeFile(inputPath, Buffer.from(bytes));

    const points = await findMotionPoints(inputPath);
    console.log("Detected motion points:", points.slice(0, 30));

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

