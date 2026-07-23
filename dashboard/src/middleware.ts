import { withAuth } from "next-auth/middleware";

export default withAuth({
  pages: { signIn: "/login" },
});

export const config = {
  matcher: [
    "/",
    "/incidents/:path*",
    "/data-quality/:path*",
    "/telemetry/:path*",
    "/pipeline/:path*",
    "/api/gateway/:path*",
    "/api/stream/:path*",
    "/api/pipeline",
    "/api/metrics/:path*",
  ],
};
