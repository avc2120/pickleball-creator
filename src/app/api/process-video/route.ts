import { NextRequest } from "next/server";
import { writeFile, readFile, unlink } from "fs/promises";
import { spawn } from "child_process";
import { execFile } from "child_process";
import { promisify } from "util";
import path from "path";
import os from "os";
import crypto from "crypto";
import * as fs from "fs/promises";

export const runtime = "nodejs";
const execFileAsync = promisify(execFile);

function runFfmpeg(inputPath: string, outputPath: string, avgCenterX: number | null) {
  return new Promise<void>((resolve, reject) => {
    const cropX =
      avgCenterX === null
        ? "(iw-1080)/2"
        : String(Math.max(0, Math.min(1920 - 1080, avgCenterX - 540)));

    const args = [
      "-i",
      inputPath,
      "-vf",
      `scale=-2:1920,crop=1080:1920:${cropX}:0`,
      "-c:v",
      "libx264",
      "-preset",
      "fast",
      "-crf",
      "23",
      "-c:a",
      "aac",
      "-y",
      outputPath,
    ];

    const ffmpeg = spawn("ffmpeg", args);

    let stderr = "";
    ffmpeg.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    ffmpeg.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(stderr));
    });
  });
}

type MotionPoint = {
  t: number;
  centerX: number;
  centerY?: number;
};

async function findMotionPoints(inputPath: string): Promise<MotionPoint[]> {
  try {
    const pythonPath = path.join(
      process.cwd(),
      "yolo-env",
      "bin",
      "python"
    );

    const scriptPath = path.join(
      process.cwd(),
      "scripts",
      "find_ball_crop.py"
    );

    const { stdout, stderr } = await execFileAsync(pythonPath, [
      scriptPath,
      inputPath,
    ], {
      maxBuffer: 20 * 1024 * 1024,
    });

    if (stderr) {
      console.error("Python detector stderr:", stderr);
    }

    const rawOutput = stdout.trim();
    const firstBrace = rawOutput.indexOf("{");
    const jsonText = firstBrace !== -1 ? rawOutput.slice(firstBrace) : rawOutput;

    try {
      const result = JSON.parse(jsonText);
      const pts = Array.isArray(result.points) ? result.points : [];

      return pts
        .map((p: any) => {
          const t = typeof p.t === "number" ? p.t : parseFloat(p.t) || 0;
          const centerX =
            typeof p.centerX === "number"
              ? p.centerX
              : typeof p.ballX === "number"
              ? p.ballX
              : null;
          const centerY = typeof p.centerY === "number" ? p.centerY : null;
          return {
            t,
            centerX,
            centerY,
          } as MotionPoint;
        })
        .filter((p: any) => p.centerX !== null && Number.isFinite(p.centerX));
    } catch (parseError) {
      console.error("Detection failed to parse JSON", {
        error: parseError,
        rawOutput,
        stderr,
      });
      return [];
    }
  } catch (error) {
    console.error("Detection failed", error);
    return [];
  }
}

function runCommand(command: string, args: string[]) {
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

async function runFfmpegDynamic(
  inputPath: string,
  outputPath: string,
  points: MotionPoint[]
) {
  const segmentSeconds = 2.0; // 2s segments = very smooth camera transitions
  const duration = Math.ceil(Math.max(...points.map((p) => p.t), 1));
  const tempDir = path.join(os.tmpdir(), crypto.randomUUID());

  await fs.mkdir(tempDir, { recursive: true });

  const segmentPaths: string[] = [];
  const cropWidth = 1080;
  const cropHeight = 1920;
  const scaledWidth = 1920;

  let index = 0;

  for (let start = 0; start < duration; start += segmentSeconds) {
    const nearby = points.filter(
      (p) => p.t >= start && p.t < start + segmentSeconds
    );

    const avgCenterX =
      nearby.length > 0
        ? Math.round(
            nearby.reduce((sum, p) => sum + p.centerX, 0) / nearby.length
          )
        : scaledWidth / 2;


    const segmentPath = path.join(tempDir, `segment-${index}.mp4`);
    segmentPaths.push(segmentPath);


    await runCommand("ffmpeg", [
      "-ss",
      String(start),
      "-t",
      String(segmentSeconds),
      "-i",
      inputPath,
      "-vf",
      `scale=-2:${cropHeight},crop=${cropWidth}:${cropHeight}:${avgCenterX}:0`,
      "-c:v",
      "libx264",
      "-g",
      "5",
      "-preset",
      "medium",
      "-crf",
      "22",
      "-c:a",
      "aac",
      "-b:a",
      "128k",
      "-y",
      segmentPath,
    ]);

    index++;
  }

  const concatFile = path.join(tempDir, "concat.txt");

  await fs.writeFile(
    concatFile,
    segmentPaths.map((p) => `file '${p}'`).join("\n")
  );

  await runCommand("ffmpeg", [
    "-f",
    "concat",
    "-safe",
    "0",
    "-i",
    concatFile,
    "-c:v",
    "copy",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    "-y",
    outputPath,
  ]);
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

  const id = crypto.randomUUID();
  const inputPath = path.join(os.tmpdir(), `${id}-input.mp4`);
  const outputPath = path.join(os.tmpdir(), `${id}-output.mp4`);

  try {
    const bytes = await file.arrayBuffer();
    await writeFile(inputPath, Buffer.from(bytes));
    const points = await findMotionPoints(inputPath);
    console.log("Detected motion points:", points.slice(0, 30));
    await runFfmpegDynamic(inputPath, outputPath, points);

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
    await unlink(inputPath).catch(() => {});
    await unlink(outputPath).catch(() => {});
  }
}

