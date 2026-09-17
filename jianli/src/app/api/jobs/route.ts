import { NextResponse } from "next/server";

// FastAPI is the sole authenticated job write path.
export async function POST() {
  return NextResponse.json({ error: "旧岗位发布接口已关闭，请使用受保护的后端岗位接口。" }, { status: 410 });
}
