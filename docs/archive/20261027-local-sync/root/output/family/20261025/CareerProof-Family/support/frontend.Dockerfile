FROM public.ecr.aws/docker/library/node:22.23.1-bookworm-slim AS build
WORKDIR /opt/careerproof/jianli
ENV NEXT_TELEMETRY_DISABLED=1 BACKEND_ORIGIN=http://database:8000
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build && npm prune --omit=dev --no-audit --no-fund && npm cache clean --force
FROM public.ecr.aws/docker/library/node:22.23.1-bookworm-slim
WORKDIR /opt/careerproof/jianli
ENV NEXT_TELEMETRY_DISABLED=1 BACKEND_ORIGIN=http://database:8000 NODE_ENV=production
LABEL org.opencontainers.image.revision=8ca91cc2c8e32fbd59412134798eb7db257a29d4
COPY --from=build /opt/careerproof/jianli/package.json ./
COPY --from=build /opt/careerproof/jianli/next.config.mjs ./
COPY --from=build /opt/careerproof/jianli/node_modules ./node_modules
COPY --from=build /opt/careerproof/jianli/.next ./.next
COPY --from=build /opt/careerproof/jianli/public ./public
EXPOSE 3000
CMD ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
