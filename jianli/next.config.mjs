const backendOrigin = (process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  ""
);

// Isolated E2E runs (scripts/Start-E2E.ps1) set NEXT_DIST_DIR (e.g. ".next-e2e")
// so their build output never touches the product build in ".next". Unset, this
// behaves exactly as before; only sibling dot-directories are accepted so the
// product build directory and paths outside the project stay unreachable.
const nextDistDir = process.env.NEXT_DIST_DIR;
if (nextDistDir != null && (nextDistDir === ".next" || !/^\.[a-z0-9-]+$/.test(nextDistDir))) {
  throw new Error(
    `NEXT_DIST_DIR must match ^\\.[a-z0-9-]+$ and differ from ".next"; got "${nextDistDir}"`
  );
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...(nextDistDir ? { distDir: nextDistDir } : {}),
  async headers() {
    const headers = [
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    ];
    // next start also serves the local HTTP demo. Enable HSTS only when the
    // operator explicitly deploys this production build behind HTTPS.
    if (process.env.NODE_ENV === "production" && process.env.CAREERPROOF_HTTPS === "true") {
      headers.push({ key: "Strict-Transport-Security", value: "max-age=31536000" });
    }
    return [{ source: "/:path*", headers }];
  },
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${backendOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;
