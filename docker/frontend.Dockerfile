FROM node:20-alpine

WORKDIR /app

COPY web/frontend/package.json ./package.json
RUN npm install

COPY web/frontend/ ./

EXPOSE 5173

CMD ["npm", "run", "dev"]
