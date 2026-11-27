FROM node:20-alpine
# Prisma's engines need OpenSSL on Alpine
RUN apk add --no-cache openssl
WORKDIR /app
COPY package*.json ./
COPY prisma ./prisma
RUN npm ci || npm install
RUN npx prisma generate
COPY . .
ENV NODE_ENV=production
EXPOSE 3000
CMD ["node", "server.js"]
