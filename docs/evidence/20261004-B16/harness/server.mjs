// 仅本机回环的静态服务器，用于 B-16 复现页；不监听外网。
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
const root = new URL(".", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const types = { ".html": "text/html; charset=utf-8" };
createServer(async (req, res) => {
  const name = new URL(req.url, "http://x").pathname === "/" ? "index.html" : new URL(req.url, "http://x").pathname.slice(1);
  try {
    const body = await readFile(join(root, decodeURIComponent(name)));
    const ext = "." + join(name).split(".").pop();
    res.writeHead(200, { "content-type": types[ext] ?? "application/octet-stream" });
    res.end(body);
  } catch { res.writeHead(404); res.end("not found"); }
}).listen(8931, "127.0.0.1", () => console.log("B16 repro server on http://127.0.0.1:8931"));
