import type { NextConfig } from "next";

function getApiBaseUrl() {
  // 优先使用环境变量
  const configured =
    process.env.NEXT_SERVER_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL;
  
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  
  // 开发/隧道环境：通过环境变量设置后端隧道地址
  // 生产环境：使用相对路径（走 rewrites 代理）
  return "";
}

const nextConfig: NextConfig = {
  basePath: '',
  allowedDevOrigins: ['*.trycloudflare.com', 'localhost'],
  reactStrictMode: false,
  
  // 只在没有设置 API_BASE_URL 时才启用 rewrites 代理
  async rewrites() {
    const apiBaseUrl = getApiBaseUrl();
    
    // 如果设置了环境变量，说明要直连后端，不启用代理
    if (apiBaseUrl && apiBaseUrl.startsWith('http')) {
      return [];
    }
    
    // 否则使用代理
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;