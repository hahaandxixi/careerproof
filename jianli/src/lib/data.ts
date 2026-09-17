import type { Candidate, Job } from "./types";

/**
 * 演示种子数据（明确标记为演示数据，不依赖爬虫）
 * 三个候选人分别演示三种匹配情形：
 *   张三 = 后端岗高匹配（证据充分）
 *   李四 = 前端岗高匹配（证据充分）
 *   王五 = 简历声明多但代码证据不足（claimed_only / gap 占主导）
 */

export const jobs: Job[] = [
  {
    id: "job-backend",
    title: "后端开发工程师",
    company: "云帆科技",
    description:
      "负责校园二手交易平台的服务端开发，涉及数据库建模、接口设计与缓存优化。",
    requirements: [
      { id: "b1", title: "熟悉 MySQL 数据库设计与查询优化", skill: "MySQL", weight: 5 },
      { id: "b2", title: "使用 Java 进行服务端开发", skill: "Java", weight: 5 },
      { id: "b3", title: "掌握 Spring Boot 框架", skill: "Spring Boot", weight: 4 },
      { id: "b4", title: "具备 REST API 接口设计能力", skill: "REST API", weight: 4 },
      { id: "b5", title: "了解 Redis 缓存", skill: "Redis", weight: 3 },
      { id: "b6", title: "了解 Docker 容器化部署", skill: "Docker", weight: 2 },
    ],
  },
  {
    id: "job-frontend",
    title: "前端开发工程师",
    company: "星河互联",
    description:
      "负责面向用户的产品前端开发，使用 React 与 TypeScript 构建高性能界面。",
    requirements: [
      { id: "f1", title: "熟练掌握 React", skill: "React", weight: 5 },
      { id: "f2", title: "使用 TypeScript 进行开发", skill: "TypeScript", weight: 5 },
      { id: "f3", title: "了解 Node.js 构建工具链", skill: "Node.js", weight: 3 },
      { id: "f4", title: "具备 REST API 对接能力", skill: "REST API", weight: 3 },
      { id: "f5", title: "熟悉 Git 协作与 CI", skill: "Git", weight: 2 },
    ],
  },
];

export const candidates: Candidate[] = [
  {
    id: "cand-zhangsan",
    name: "张三",
    school: "示例大学",
    major: "计算机科学与技术",
    resumeText:
      "张三，邮箱 zhangsan@example.com，电话 13800138000。\n" +
      "熟悉 Java 服务端开发，使用 Spring Boot 构建 REST API 接口。\n" +
      "熟悉 MySQL 数据库设计与查询优化，了解 Redis 缓存，了解 Docker 容器化部署。",
    projects: [
      {
        id: "proj-shop",
        name: "校园二手交易平台（后端）",
        description: "基于 Spring Boot + MySQL + Redis 的交易平台后端",
        files: [
          {
            path: "src/main/resources/schema.sql",
            content:
              "CREATE TABLE users (\n" +
              "  id BIGINT PRIMARY KEY AUTO_INCREMENT,\n" +
              "  name VARCHAR(64) NOT NULL,\n" +
              "  email VARCHAR(128) UNIQUE\n" +
              ");\n" +
              "CREATE TABLE orders (\n" +
              "  id BIGINT PRIMARY KEY AUTO_INCREMENT,\n" +
              "  buyer_id BIGINT,\n" +
              "  amount DECIMAL(10,2),\n" +
              "  FOREIGN KEY (buyer_id) REFERENCES users(id)\n" +
              ");\n" +
              "INSERT INTO users (name, email) VALUES ('demo', 'demo@example.com');\n" +
              "SELECT o.id, o.amount FROM orders o INNER JOIN users u ON o.buyer_id = u.id;\n",
          },
          {
            path: "src/main/java/com/shop/UserController.java",
            content:
              "package com.shop;\n" +
              "import org.springframework.web.bind.annotation.*;\n" +
              "\n" +
              "@RestController\n" +
              "@RequestMapping(\"/api/users\")\n" +
              "public class UserController {\n" +
              "  @GetMapping(\"/{id}\")\n" +
              "  public String getUser(@PathVariable Long id) {\n" +
              "    return \"user \" + id;\n" +
              "  }\n" +
              "  @PostMapping\n" +
              "  public String createUser() {\n" +
              "    return \"created\";\n" +
              "  }\n" +
              "}\n",
          },
          {
            path: "src/main/java/com/shop/OrderService.java",
            content:
              "package com.shop;\n" +
              "import org.springframework.stereotype.Service;\n" +
              "\n" +
              "@Service\n" +
              "public class OrderService {\n" +
              "  private final RedisCache redisCache;\n" +
              "  public OrderService(RedisCache redisCache) {\n" +
              "    this.redisCache = redisCache;\n" +
              "  }\n" +
              "  public void cache(String key, String value) {\n" +
              "    redisCache.set(key, value);\n" +
              "  }\n" +
              "}\n",
          },
          {
            path: "src/main/resources/application.yml",
            content:
              "spring:\n" +
              "  datasource:\n" +
              "    url: jdbc:mysql://localhost:3306/shop\n" +
              "    username: root\n" +
              "  data:\n" +
              "    redis:\n" +
              "      host: localhost\n" +
              "      port: 6379\n",
          },
          {
            path: "pom.xml",
            content:
              "<dependencies>\n" +
              "  <dependency>spring-boot-starter-web</dependency>\n" +
              "  <dependency>mysql-connector-java</dependency>\n" +
              "  <dependency>spring-boot-starter-data-redis</dependency>\n" +
              "</dependencies>\n",
          },
          {
            path: "Dockerfile",
            content:
              "FROM openjdk:17\n" +
              "COPY target/app.jar app.jar\n" +
              "ENTRYPOINT [\"java\", \"-jar\", \"/app.jar\"]\n",
          },
        ],
      },
    ],
  },
  {
    id: "cand-lisi",
    name: "李四",
    school: "示例大学",
    major: "软件工程",
    resumeText:
      "李四，邮箱 lisi@example.com。\n" +
      "熟练掌握 React 与 TypeScript，使用 Node.js 工具链构建前端项目，具备 REST API 对接能力，熟悉 Git 协作。",
    projects: [
      {
        id: "proj-blog",
        name: "个人博客前端",
        description: "基于 Next.js + React + TypeScript 的博客前端",
        files: [
          {
            path: "app/page.tsx",
            content:
              "import React, { useState, useEffect } from 'react';\n" +
              "export default function Page() {\n" +
              "  const [posts, setPosts] = useState<string[]>([]);\n" +
              "  useEffect(() => { fetchPosts().then(setPosts); }, []);\n" +
              "  return (\n" +
              "    <main>{posts.map((p) => <p key={p}>{p}</p>)}</main>\n" +
              "  );\n" +
              "}\n",
          },
          {
            path: "lib/api.ts",
            content:
              "export async function fetchPosts(): Promise<string[]> {\n" +
              "  const res = await fetch('/api/posts');\n" +
              "  if (res.status === 200) return res.json();\n" +
              "  return [];\n" +
              "}\n",
          },
          {
            path: "package.json",
            content:
              "{\n" +
              "  \"dependencies\": {\n" +
              "    \"react\": \"19.0.0\",\n" +
              "    \"next\": \"15.1.6\",\n" +
              "    \"typescript\": \"^5\"\n" +
              "  }\n" +
              "}\n",
          },
          {
            path: "tsconfig.json",
            content:
              "{\n" +
              "  \"compilerOptions\": {\n" +
              "    \"strict\": true\n" +
              "  }\n" +
              "}\n",
          },
          {
            path: ".github/workflows/ci.yml",
            content:
              "name: CI\n" +
              "on:\n" +
              "  push:\n" +
              "    branches: [main]\n" +
              "jobs:\n" +
              "  build:\n" +
              "    steps:\n" +
              "      - run: npm ci\n",
          },
        ],
      },
    ],
  },
  {
    id: "cand-wangwu",
    name: "王五",
    school: "示例大学",
    major: "信息管理",
    resumeText:
      "王五，邮箱 wangwu@example.com。\n" +
      "熟悉 MySQL、Java、Redis、React、TypeScript、Python、Docker、Linux 等多项技术。",
    projects: [
      {
        id: "proj-course",
        name: "课程作业脚本",
        description: "一个简单的 Python 脚本",
        files: [
          {
            path: "hello.py",
            content:
              "def main():\n" +
              "    print('hello world')\n" +
              "\n" +
              "if __name__ == '__main__':\n" +
              "    main()\n",
          },
        ],
      },
    ],
  },
];
