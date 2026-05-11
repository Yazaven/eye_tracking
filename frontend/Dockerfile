FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 3000
ENV NEXT_TELEMETRY_DISABLED=1
CMD ["npx", "next", "dev", "--hostname", "0.0.0.0"]
