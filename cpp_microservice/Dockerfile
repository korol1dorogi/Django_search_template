FROM gcc:12 AS builder
WORKDIR /src
COPY main.cpp TextHandler.h TextHandler.cpp .
COPY include/json.hpp include/httplib.h ./
RUN g++ -std=c++20 -pthread -O2 main.cpp TextHandler.cpp -o microservice

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=builder /src/microservice .
EXPOSE 8080 8081
CMD ["./microservice"]