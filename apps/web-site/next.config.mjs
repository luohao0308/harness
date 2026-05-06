/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  staticPageGenerationTimeout: 180,
  experimental: {
    cpus: 1,
  },
};

export default nextConfig;
