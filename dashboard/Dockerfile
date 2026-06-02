# --- Stage 1: Build the React Application ---
FROM node:20-alpine AS build

# Set working directory for the builder
WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the frontend source code
COPY . .

# Build the Vite project (outputs into /app/dist)
RUN npm run build

# --- Stage 2: Serve with Nginx ---
FROM nginx:alpine

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy the built React assets from the build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy our custom Nginx proxy configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Run Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
