const backendOrigin = (process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  ""
);

/** @type {import('next').NextConfig} */
const nextConfig = {
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
