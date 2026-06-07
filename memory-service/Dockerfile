FROM node:20-slim

# Build tools for better-sqlite3 native compilation
RUN apt-get update && apt-get install -y python3 make g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app/vendor/memory
COPY vendor/memory/package.json vendor/memory/tsconfig.json ./
RUN npm install
# sqlite-vec alpha bug: loadExtension path gets ".so" appended, producing "vec0.so.so".
# Create the double-extension name so the runtime find the file.
RUN find node_modules -name "vec0.so" -exec sh -c 'cp "$1" "$1.so"' _ {} \;
COPY vendor/memory/src ./src
RUN npm run build

WORKDIR /app
COPY package.json tsconfig.json ./
RUN npm install
COPY src ./src
RUN npm run build

CMD ["node", "dist/server.js"]
