# Dev-mode Dockerfile (next dev, hot reload) — good enough for the
# hackathon build/demo cycle. Swap to a `next build` + `next start`
# multi-stage image later if a production deploy is actually needed.
FROM node:22-slim

WORKDIR /app

COPY web/package.json /app/package.json
RUN npm install

COPY web/ /app/

EXPOSE 3000
CMD ["npm", "run", "dev"]
