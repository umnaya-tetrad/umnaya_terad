FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig*.json vite.config.ts ./
COPY src ./src
COPY project-context/pilot/planning/shared/ux-copy.json ./project-context/pilot/planning/shared/ux-copy.json
EXPOSE 5173
CMD ["npm", "run", "dev"]
