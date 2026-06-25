/**
 * API route that processes an uploaded video.
 *
 * Pickleball:
 * - detects player / ball motion
 * - renders a smooth vertical crop sequence
 *
 * Golf:
 * - detects swing clips
 * - cuts out downtime
 * - stitches swings together
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
const golfDetectorScript = path.join(
  process.cwd(),
  "scripts",
  "detect_golf_swings.py"
);

const ffmpegExecutable = "ffmpeg";

type Sport = "pickleball" | "golf";

type MotionPoint = {
  t: number;
  centerX: number;
  centerY?: number;
  playerSpanWidth?: number;
  playerSpanHeight?: number;
};

type Clip = {
  start: number;
  end: number;
  label?: string;
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
      else reject(new Error(stderr || `${command} failed with code ${code}`));
    });
  });
}

function safeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function safeParseNumber(value: unknown): number {
  return typeof value === "number" ? value : parseFloat(String(value)) || 0;
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
      centerX: safeNumber(point.centerX) ?? safeNumber(point.ballX) ?? null,
      centerY: safeNumber(point.centerY),
      playerSpanWidth: safeNumber(point.playerSpanWidth),
      playerSpanHeight: safeNumber(point.playerSpanHeight),
    }))
    .filter((point) => point.centerX !== null) as MotionPoint[];
}

function parseGolfDetectorOutput(stdout: string): Clip[] {
  const rawOutput = stdout.trim();
  const firstBrace = rawOutput.indexOf("{");
  const jsonText = firstBrace !== -1 ? rawOutput.slice(firstBrace) : rawOutput;
  const result = JSON.parse(jsonText);
  const clips = Array.isArray(result.clips) ? result.clips : [];

  return clips
    .map((clip: any) => ({
      start: safeParseNumber(clip.start),
      end: safeParseNumber(clip.end),
      label: typeof clip.label === "string" ? clip.label : "golf_swing",
    }))
    .filter((clip) => clip.end > clip.start);
}

async function findMotionPoints(inputPath: string): Promise<MotionPoint[]> {
  try {
    const { stdout, stderr } = await execFileAsync(
      pythonExecutable,
      [detectorScript, inputPath],
      {
        maxBuffer: 20 * 1024 * 1024,
      }
    );

    if (stderr) {
      console.error("Python detector stderr:", stderr);
    }

    return parseDetectorOutput(stdout);
  } catch (error) {
    console.error("Detection failed", error);
    return [];
  }
}

async function detectGolfSwings(inputPath: string): Promise<Clip[]> {
  try {
    const { stdout, stderr } = await execFileAsync(
      pythonExecutable,
      [golfDetectorScript, inputPath],
      {
        maxBuffer: 20 * 1024 * 1024,
      }
    );

    if (stderr) {
      console.error("Golf detector stderr:", stderr);
    }

    return parseGolfDetectorOutput(stdout);
  } catch (error) {
    console.error("Golf detection failed", error);
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

async function stitchClips(
  inputPath: string,
  clips: Clip[],
  outputPath: string
) {
  if (clips.length === 0) {
    throw new Error("No golf swings detected");
  }

  const clipPaths: string[] = [];
  const concatPath = createTempPath("concat.txt");

  try {
    for (let i = 0; i < clips.length; i++) {
      const clipPath = createTempPath(`golf-clip-${i}.mp4`);
      clipPaths.push(clipPath);

      await spawnCommand(ffmpegExecutable, [
        "-ss",
        String(clips[i].start),
        "-to",
        String(clips[i].end),
        "-i",
        inputPath,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-y",
        clipPath,
      ]);
    }

    const concatText = clipPaths
      .map((clipPath) => `file '${clipPath.replace(/'/g, "'\\''")}'`)
      .join("\n");

    await writeFile(concatPath, concatText);

    await spawnCommand(ffmpegExecutable, [
      "-f",
      "concat",
      "-safe",
      "0",
      "-i",
      concatPath,
      "-c",
      "copy",
      "-y",
      outputPath,
    ]);
  } finally {
    await cleanupPaths([...clipPaths, concatPath]);
  }
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
  const sportValue = formData.get("sport");
  const sport: Sport = sportValue === "golf" ? "golf" : "pickleball";

  if (!(file instanceof File)) {
    return Response.json({ error: "No video uploaded" }, { status: 400 });
  }

  if (file.size > 500 * 1024 * 1024) {
    return Response.json(
      { error: "File too large. Max 100MB." },
      { status: 400 }
    );
  }

  const inputPath = createTempPath("input.mp4");
  const outputPath = createTempPath("output.mp4");
  const pointsPath = createTempPath("points.json");
  const framesDir = createTempPath("frames");

  try {
    const bytes = await file.arrayBuffer();
    await writeFile(inputPath, Buffer.from(bytes));

    if (sport === "golf") {
      const clips = await detectGolfSwings(inputPath);
      console.log("Detected golf swings:", clips);

      await stitchClips(inputPath, clips, outputPath);
    } else {
      const points = await findMotionPoints(inputPath);
      console.log("Detected motion points:", points.slice(0, 30));

      await writeFile(pointsPath, JSON.stringify({ points }));
      await renderFrames(inputPath, pointsPath, framesDir);
      await encodeVideo(framesDir, inputPath, outputPath);
    }

    const outputBuffer = await readFile(outputPath);
    const filename =
      sport === "golf" ? "golf-swing-montage.mp4" : "pickleball-reel.mp4";

    return new Response(outputBuffer, {
      headers: {
        "Content-Type": "video/mp4",
        "Content-Disposition": `attachment; filename="${filename}"`,
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